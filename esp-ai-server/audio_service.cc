#include "audio_service.h"
#include <esp_log.h>
#include <cstring>

#if CONFIG_USE_AUDIO_PROCESSOR
#include "processors/afe_audio_processor.h"
#else
#include "processors/no_audio_processor.h"
#endif

#if CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32P4
#include "wake_words/afe_wake_word.h"
#include "wake_words/custom_wake_word.h"
#else
#include "wake_words/esp_wake_word.h"
#endif

#define TAG "AudioService"


AudioService::AudioService() {
    event_group_ = xEventGroupCreate();
}

AudioService::~AudioService() {
    if (event_group_ != nullptr) {
        vEventGroupDelete(event_group_);
    }
}


void AudioService::Initialize(AudioCodec* codec) {
    codec_ = codec;
    codec_->Start();

    /* Setup the audio codec */
    opus_decoder_ = std::make_unique<OpusDecoderWrapper>(codec->output_sample_rate(), 1, OPUS_FRAME_DURATION_MS);
    opus_encoder_ = std::make_unique<OpusEncoderWrapper>(16000, 1, OPUS_FRAME_DURATION_MS);
    opus_encoder_->SetComplexity(0);

    // 硬件和软件都使用16kHz，不需要重采样
    ESP_LOGI(TAG, "音频配置: 输入=%dHz, 输出=%dHz, 编码器=16000Hz", 
             codec->input_sample_rate(), codec->output_sample_rate());

#if CONFIG_USE_AUDIO_PROCESSOR
    audio_processor_ = std::make_unique<AfeAudioProcessor>();
#else
    audio_processor_ = std::make_unique<NoAudioProcessor>();
#endif

    audio_processor_->OnOutput([this](std::vector<int16_t>&& data) {
        // 硬件直接输出16kHz数据，无需重采样
        PushTaskToEncodeQueue(kAudioTaskTypeEncodeToSendQueue, std::move(data));
    });

    audio_processor_->OnVadStateChange([this](bool speaking) {
        voice_detected_ = speaking;
        if (callbacks_.on_vad_change) {
            callbacks_.on_vad_change(speaking);
        }
    });

    esp_timer_create_args_t audio_power_timer_args = {
        .callback = [](void* arg) {
            AudioService* audio_service = (AudioService*)arg;
            audio_service->CheckAndUpdateAudioPowerState();
        },
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "audio_power_timer",
        .skip_unhandled_events = true,
    };
    esp_timer_create(&audio_power_timer_args, &audio_power_timer_);
}

void AudioService::Start() {
    service_stopped_ = false;
    
    // 清空所有音频队列，确保干净的启动状态
    {
        std::lock_guard<std::mutex> lock(audio_queue_mutex_);
        audio_decode_queue_.clear();
        audio_playback_queue_.clear();
        audio_encode_queue_.clear();
        audio_send_queue_.clear();
        audio_testing_queue_.clear();
    }
    
    /* Create the audio power timer */
    esp_timer_create_args_t timer_args = {
        .callback = [](void* arg) {
            AudioService* audio_service = (AudioService*)arg;
            audio_service->CheckAndUpdateAudioPowerState();
        },
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "audio_power_timer",
        .skip_unhandled_events = true
    };
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &audio_power_timer_));

    esp_timer_start_periodic(audio_power_timer_, 1000000);

#if CONFIG_USE_AUDIO_PROCESSOR
    /* Start the audio input task */
    xTaskCreatePinnedToCore([](void* arg) {
        AudioService* audio_service = (AudioService*)arg;
        audio_service->AudioInputTask();
        vTaskDelete(NULL);
    }, "audio_input", 2048 * 3, this, 8, &audio_input_task_handle_, 0);

    /* Start the audio output task */
    xTaskCreate([](void* arg) {
        AudioService* audio_service = (AudioService*)arg;
        audio_service->AudioOutputTask();
        vTaskDelete(NULL);
    }, "audio_output", 2048 * 2, this, 4, &audio_output_task_handle_);
#else
    /* Start the audio input task */
    xTaskCreate([](void* arg) {
        AudioService* audio_service = (AudioService*)arg;
        audio_service->AudioInputTask();
        vTaskDelete(NULL);
    }, "audio_input", 2048 * 2, this, 8, &audio_input_task_handle_);

    /* Start the audio output task */
    xTaskCreate([](void* arg) {
        AudioService* audio_service = (AudioService*)arg;
        audio_service->AudioOutputTask();
        vTaskDelete(NULL);
    }, "audio_output", 2048, this, 4, &audio_output_task_handle_);
#endif

    /* Start the opus codec task */
    xTaskCreate([](void* arg) {
        AudioService* audio_service = (AudioService*)arg;
        audio_service->OpusCodecTask();
        vTaskDelete(NULL);
    }, "opus_codec", 2048 * 13, this, 2, &opus_codec_task_handle_);
}

void AudioService::Stop() {
    esp_timer_stop(audio_power_timer_);
    service_stopped_ = true;
    xEventGroupSetBits(event_group_, AS_EVENT_AUDIO_TESTING_RUNNING |
        AS_EVENT_WAKE_WORD_RUNNING |
        AS_EVENT_AUDIO_PROCESSOR_RUNNING);

    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    audio_encode_queue_.clear();
    audio_decode_queue_.clear();
    audio_playback_queue_.clear();
    audio_testing_queue_.clear();
    audio_queue_cv_.notify_all();
}

bool AudioService::ReadAudioData(std::vector<int16_t>& data, int sample_rate, int samples) {
    if (!codec_->input_enabled()) {
        esp_timer_stop(audio_power_timer_);
        esp_timer_start_periodic(audio_power_timer_, AUDIO_POWER_CHECK_INTERVAL_MS * 1000);
        codec_->EnableInput(true);
    }

    // 硬件和软件都使用相同采样率，直接读取数据
    data.resize(samples * codec_->input_channels());
    if (!codec_->InputData(data)) {
        return false;
    }

    /* Update the last input time */
    last_input_time_ = std::chrono::steady_clock::now();
    debug_statistics_.input_count++;

#if CONFIG_USE_AUDIO_DEBUGGER
    // 音频调试：发送原始音频数据
    if (audio_debugger_ == nullptr) {
        audio_debugger_ = std::make_unique<AudioDebugger>();
    }
    audio_debugger_->Feed(data);
#endif

    return true;
}

void AudioService::AudioInputTask() {
    while (true) {
        EventBits_t bits = xEventGroupWaitBits(event_group_, AS_EVENT_AUDIO_TESTING_RUNNING |
            AS_EVENT_WAKE_WORD_RUNNING | AS_EVENT_AUDIO_PROCESSOR_RUNNING,
            pdFALSE, pdFALSE, portMAX_DELAY);

        if (service_stopped_) {
            break;
        }
        if (audio_input_need_warmup_) {
            audio_input_need_warmup_ = false;
            vTaskDelay(pdMS_TO_TICKS(120));
            continue;
        }

        /* Used for audio testing in NetworkConfiguring mode by clicking the BOOT button */
        if (bits & AS_EVENT_AUDIO_TESTING_RUNNING) {
            if (audio_testing_queue_.size() >= AUDIO_TESTING_MAX_DURATION_MS / OPUS_FRAME_DURATION_MS) {
                ESP_LOGW(TAG, "Audio testing queue is full, stopping audio testing");
                EnableAudioTesting(false);
                continue;
            }
            std::vector<int16_t> data;
            int samples = OPUS_FRAME_DURATION_MS * 16000 / 1000;
            if (ReadAudioData(data, 16000, samples)) {
                // If input channels is 2, we need to fetch the left channel data
                if (codec_->input_channels() == 2) {
                    auto mono_data = std::vector<int16_t>(data.size() / 2);
                    for (size_t i = 0, j = 0; i < mono_data.size(); ++i, j += 2) {
                        mono_data[i] = data[j];
                    }
                    data = std::move(mono_data);
                }
                PushTaskToEncodeQueue(kAudioTaskTypeEncodeToTestingQueue, std::move(data));
                continue;
            }
        }

        /* Feed the wake word */
        if (bits & AS_EVENT_WAKE_WORD_RUNNING) {
            std::vector<int16_t> data;
            int samples = wake_word_->GetFeedSize();
            if (samples > 0) {
                if (ReadAudioData(data, 16000, samples)) {
                    wake_word_->Feed(data);
                    continue;
                }
            }
        }

        /* Feed the audio processor */
        if (bits & AS_EVENT_AUDIO_PROCESSOR_RUNNING) {
            std::vector<int16_t> data;
            int samples = audio_processor_->GetFeedSize();
            if (samples > 0) {
                if (ReadAudioData(data, 16000, samples)) {
                    // 调试：检查原始音频输入数据是否在变化
                    static uint32_t last_input_checksum = 0;
                    static int input_frame_count = 0;
                    uint32_t input_checksum = 0;
                    if (!data.empty()) {
                        for (size_t i = 0; i < std::min(data.size(), (size_t)32); i++) {
                            input_checksum += (uint32_t)data[i] * (i + 1);
                        }
                    }
                    
                    input_frame_count++;
                    if (input_frame_count % 50 == 0) {  // 每50帧打印一次（约2秒）
                        ESP_LOGI(TAG, "🎤 [DEBUG] 音频输入检查: 帧#%d, 大小=%u, 校验和=0x%08X, 前4个样本=[%d,%d,%d,%d]", 
                                 input_frame_count, (unsigned int)data.size(), input_checksum,
                                 data.size() > 0 ? data[0] : 0,
                                 data.size() > 1 ? data[1] : 0,
                                 data.size() > 2 ? data[2] : 0,
                                 data.size() > 3 ? data[3] : 0);
                        
                        if (input_checksum == last_input_checksum && last_input_checksum != 0) {
                            ESP_LOGW(TAG, "⚠️ [DEBUG] 检测到重复的音频输入数据！校验和连续相同: 0x%08X", input_checksum);
                        }
                    }
                    last_input_checksum = input_checksum;
                    
                    audio_processor_->Feed(std::move(data));
                    continue;
                }
            }
        }

        ESP_LOGE(TAG, "Should not be here, bits: %lx", bits);
        break;
    }

    ESP_LOGW(TAG, "Audio input task stopped");
}

void AudioService::AudioOutputTask() {
    while (true) {
        std::unique_lock<std::mutex> lock(audio_queue_mutex_);
        audio_queue_cv_.wait(lock, [this]() { return !audio_playback_queue_.empty() || service_stopped_; });
        if (service_stopped_) {
            break;
        }

        auto task = std::move(audio_playback_queue_.front());
        audio_playback_queue_.pop_front();
        audio_queue_cv_.notify_all();
        lock.unlock();

        if (!codec_->output_enabled()) {
            esp_timer_stop(audio_power_timer_);
            esp_timer_start_periodic(audio_power_timer_, AUDIO_POWER_CHECK_INTERVAL_MS * 1000);
            codec_->EnableOutput(true);
        }
        
        codec_->OutputData(task->pcm);

        /* Update the last output time */
        last_output_time_ = std::chrono::steady_clock::now();
        debug_statistics_.playback_count++;

#if CONFIG_USE_SERVER_AEC
        /* Record the timestamp for server AEC */
        if (task->timestamp > 0) {
            lock.lock();
            timestamp_queue_.push_back(task->timestamp);
        }
#endif
    }

    ESP_LOGW(TAG, "Audio output task stopped");
}

void AudioService::OpusCodecTask() {
    while (true) {
        std::unique_lock<std::mutex> lock(audio_queue_mutex_);
        audio_queue_cv_.wait(lock, [this]() {
            return service_stopped_ ||
                (!audio_encode_queue_.empty() && audio_send_queue_.size() < MAX_SEND_PACKETS_IN_QUEUE) ||
                (!audio_decode_queue_.empty() && audio_playback_queue_.size() < MAX_PLAYBACK_TASKS_IN_QUEUE);
        });
        if (service_stopped_) {
            break;
        }

        /* Decode the audio from decode queue */
        if (!audio_decode_queue_.empty() && audio_playback_queue_.size() < MAX_PLAYBACK_TASKS_IN_QUEUE) {
            
            auto packet = std::move(audio_decode_queue_.front());
            audio_decode_queue_.pop_front();
            audio_queue_cv_.notify_all();
            lock.unlock();

            // 验证音频包数据的有效性
            if (packet->payload.empty()) {
                lock.lock();
                continue;
            }
            
            if (packet->sample_rate < 8000 || packet->sample_rate > 48000) {
                lock.lock();
                continue;
            }
            
            if (packet->frame_duration < 10 || packet->frame_duration > 120) {
                lock.lock();
                continue;
            }
            
            auto task = std::make_unique<AudioTask>();
            task->type = kAudioTaskTypeDecodeToPlaybackQueue;
            task->timestamp = packet->timestamp;

            SetDecodeSampleRate(packet->sample_rate, packet->frame_duration);
            if (opus_decoder_->Decode(std::move(packet->payload), task->pcm)) {
                // Resample if the sample rate is different
                if (opus_decoder_->sample_rate() != codec_->output_sample_rate()) {
                    int target_size = output_resampler_.GetOutputSamples(task->pcm.size());
                    std::vector<int16_t> resampled(target_size);
                    output_resampler_.Process(task->pcm.data(), task->pcm.size(), resampled.data());
                    task->pcm = std::move(resampled);
                }

                lock.lock();
                audio_playback_queue_.push_back(std::move(task));
                audio_queue_cv_.notify_all();
            } else {
                lock.lock();
            }
            debug_statistics_.decode_count++;
        }
        
        /* Encode the audio to send queue */
        if (!audio_encode_queue_.empty() && audio_send_queue_.size() < MAX_SEND_PACKETS_IN_QUEUE) {
            auto task = std::move(audio_encode_queue_.front());
            audio_encode_queue_.pop_front();
            audio_queue_cv_.notify_all();
            lock.unlock();

            auto packet = std::make_unique<AudioStreamPacket>();
            packet->frame_duration = OPUS_FRAME_DURATION_MS;
            packet->sample_rate = 16000;  // 使用16kHz采样率
            packet->timestamp = task->timestamp;
            
            // 调试：检查PCM数据是否在变化
            static uint32_t last_pcm_checksum = 0;
            uint32_t pcm_checksum = 0;
            if (!task->pcm.empty()) {
                for (size_t i = 0; i < std::min(task->pcm.size(), (size_t)32); i++) {
                    pcm_checksum += (uint32_t)task->pcm[i] * (i + 1);
                }
            }
            
            if (debug_statistics_.encode_count % 10 == 0) {
                ESP_LOGI(TAG, "🔍 [DEBUG] PCM数据检查: 帧#%d, PCM大小=%u, 校验和=0x%08X, 前4个样本=[%d,%d,%d,%d]", 
                         debug_statistics_.encode_count, (unsigned int)task->pcm.size(), pcm_checksum,
                         task->pcm.size() > 0 ? task->pcm[0] : 0,
                         task->pcm.size() > 1 ? task->pcm[1] : 0,
                         task->pcm.size() > 2 ? task->pcm[2] : 0,
                         task->pcm.size() > 3 ? task->pcm[3] : 0);
                
                if (pcm_checksum == last_pcm_checksum && last_pcm_checksum != 0) {
                    ESP_LOGW(TAG, "⚠️ [DEBUG] 检测到重复的PCM数据！校验和连续相同: 0x%08X", pcm_checksum);
                }
            }
            last_pcm_checksum = pcm_checksum;
            
            if (!opus_encoder_->Encode(std::move(task->pcm), packet->payload)) {
                ESP_LOGE(TAG, "Failed to encode audio");
                continue;
            }

            if (task->type == kAudioTaskTypeEncodeToSendQueue) {
                // 在move之前保存payload大小
                size_t payload_size = packet->payload.size();
                
                // 调试：检查Opus编码输出是否在变化
                static uint32_t last_opus_checksum = 0;
                uint32_t opus_checksum = 0;
                if (!packet->payload.empty()) {
                    for (size_t i = 0; i < std::min(packet->payload.size(), (size_t)32); i++) {
                        opus_checksum += (uint32_t)packet->payload[i] * (i + 1);
                    }
                }
                
                if (debug_statistics_.encode_count % 10 == 0) {
                    ESP_LOGI(TAG, "🔍 [DEBUG] Opus数据检查: 帧#%d, Opus大小=%u, 校验和=0x%08X, 前8字节=[%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X]", 
                             debug_statistics_.encode_count, (unsigned int)payload_size, opus_checksum,
                             packet->payload.size() > 0 ? packet->payload[0] : 0,
                             packet->payload.size() > 1 ? packet->payload[1] : 0,
                             packet->payload.size() > 2 ? packet->payload[2] : 0,
                             packet->payload.size() > 3 ? packet->payload[3] : 0,
                             packet->payload.size() > 4 ? packet->payload[4] : 0,
                             packet->payload.size() > 5 ? packet->payload[5] : 0,
                             packet->payload.size() > 6 ? packet->payload[6] : 0,
                             packet->payload.size() > 7 ? packet->payload[7] : 0);
                    
                    if (opus_checksum == last_opus_checksum && last_opus_checksum != 0) {
                        ESP_LOGW(TAG, "⚠️ [DEBUG] 检测到重复的Opus数据！校验和连续相同: 0x%08X", opus_checksum);
                    }
                }
                last_opus_checksum = opus_checksum;
                
                // 检查编码后的数据是否异常 - 静音数据包通常很小
                if (payload_size < 10) {
                    // 静默跳过小包，避免刷屏（每100个小包才报告一次）
                    static int small_packet_count = 0;
                    small_packet_count++;
                    if (small_packet_count % 100 == 1) {
                        ESP_LOGW(TAG, "⚠️ Skipping small Opus packets (< 10 bytes), count: %d", small_packet_count);
                    }
                    continue;  // 跳过异常的包
                }
                
                // 检测静音数据包：如果Opus数据只有1字节且为0x50，则跳过
                if (payload_size == 1 && packet->payload[0] == 0x50) {
                    static int silence_packet_count = 0;
                    silence_packet_count++;
                    if (silence_packet_count % 50 == 1) {
                        ESP_LOGD(TAG, "🔇 Skipping silence Opus packets, count: %d", silence_packet_count);
                    }
                    continue;  // 跳过静音包
                }
                
                {
                    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
                    audio_send_queue_.push_back(std::move(packet));
                }
                
                // 每10个包打印一次日志，避免日志过多
                if (debug_statistics_.encode_count % 10 == 0) {
                    ESP_LOGI(TAG, "📦 Opus encoded: packet #%d, payload size: %u bytes, send queue: %u", 
                             debug_statistics_.encode_count, (unsigned int)payload_size, (unsigned int)audio_send_queue_.size());
                }
                if (callbacks_.on_send_queue_available) {
                    callbacks_.on_send_queue_available();
                }
            } else if (task->type == kAudioTaskTypeEncodeToTestingQueue) {
                std::lock_guard<std::mutex> lock(audio_queue_mutex_);
                audio_testing_queue_.push_back(std::move(packet));
            }
            debug_statistics_.encode_count++;
            lock.lock();
        }
    }

    ESP_LOGW(TAG, "Opus codec task stopped");
}

void AudioService::SetDecodeSampleRate(int sample_rate, int frame_duration) {
    if (opus_decoder_->sample_rate() == sample_rate && opus_decoder_->duration_ms() == frame_duration) {
        return;
    }

    opus_decoder_.reset();
    opus_decoder_ = std::make_unique<OpusDecoderWrapper>(sample_rate, 1, frame_duration);

    auto codec = Board::GetInstance().GetAudioCodec();
    if (opus_decoder_->sample_rate() != codec->output_sample_rate()) {
        ESP_LOGI(TAG, "Resampling audio from %d to %d", opus_decoder_->sample_rate(), codec->output_sample_rate());
        output_resampler_.Configure(opus_decoder_->sample_rate(), codec->output_sample_rate());
    }
}

void AudioService::PushTaskToEncodeQueue(AudioTaskType type, std::vector<int16_t>&& pcm) {
    auto task = std::make_unique<AudioTask>();
    task->type = type;
    task->pcm = std::move(pcm);
    
    /* Push the task to the encode queue */
    std::unique_lock<std::mutex> lock(audio_queue_mutex_);

    /* If the task is to send queue, we need to set the timestamp */
    if (type == kAudioTaskTypeEncodeToSendQueue && !timestamp_queue_.empty()) {
        if (timestamp_queue_.size() <= MAX_TIMESTAMPS_IN_QUEUE) {
            task->timestamp = timestamp_queue_.front();
        } else {
            ESP_LOGW(TAG, "Timestamp queue (%u) is full, dropping timestamp", timestamp_queue_.size());
        }
        timestamp_queue_.pop_front();
    }

    audio_queue_cv_.wait(lock, [this]() { return audio_encode_queue_.size() < MAX_ENCODE_TASKS_IN_QUEUE; });
    audio_encode_queue_.push_back(std::move(task));
    audio_queue_cv_.notify_all();
}

bool AudioService::PushPacketToDecodeQueue(std::unique_ptr<AudioStreamPacket> packet, bool wait) {
    std::unique_lock<std::mutex> lock(audio_queue_mutex_);
    if (audio_decode_queue_.size() >= MAX_DECODE_PACKETS_IN_QUEUE) {
        if (wait) {
            audio_queue_cv_.wait(lock, [this]() { return audio_decode_queue_.size() < MAX_DECODE_PACKETS_IN_QUEUE; });
        } else {
            return false;
        }
    }
    audio_decode_queue_.push_back(std::move(packet));
    audio_queue_cv_.notify_all();
    return true;
}

std::unique_ptr<AudioStreamPacket> AudioService::PopPacketFromSendQueue() {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    if (audio_send_queue_.empty()) {
        return nullptr;
    }
    auto packet = std::move(audio_send_queue_.front());
    audio_send_queue_.pop_front();
    audio_queue_cv_.notify_all();
    return packet;
}

void AudioService::ClearSendQueue() {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    if (!audio_send_queue_.empty()) {
        // 只在队列积压较多时才显示警告，避免刷屏
        if (audio_send_queue_.size() > 5) {
            ESP_LOGW(TAG, "🗑️ Clearing send queue: %u packets discarded", (unsigned int)audio_send_queue_.size());
        } else {
            ESP_LOGD(TAG, "🗑️ Clearing send queue: %u packets discarded", (unsigned int)audio_send_queue_.size());
        }
        audio_send_queue_.clear();
        audio_queue_cv_.notify_all();
    }
}

void AudioService::EncodeWakeWord() {
    if (wake_word_) {
        wake_word_->EncodeWakeWordData();
    }
}

const std::string& AudioService::GetLastWakeWord() const {
    return wake_word_->GetLastDetectedWakeWord();
}

std::unique_ptr<AudioStreamPacket> AudioService::PopWakeWordPacket() {
    auto packet = std::make_unique<AudioStreamPacket>();
    if (wake_word_->GetWakeWordOpus(packet->payload)) {
        return packet;
    }
    return nullptr;
}

void AudioService::EnableWakeWordDetection(bool enable) {
    if (!wake_word_) {
        return;
    }

    ESP_LOGD(TAG, "%s wake word detection", enable ? "Enabling" : "Disabling");
    if (enable) {
        if (!wake_word_initialized_) {
            if (!wake_word_->Initialize(codec_, models_list_)) {
                ESP_LOGE(TAG, "Failed to initialize wake word");
                return;
            }
            wake_word_initialized_ = true;
        }
        wake_word_->Start();
        xEventGroupSetBits(event_group_, AS_EVENT_WAKE_WORD_RUNNING);
    } else {
        wake_word_->Stop();
        xEventGroupClearBits(event_group_, AS_EVENT_WAKE_WORD_RUNNING);
    }
}

void AudioService::EnableVoiceProcessing(bool enable) {
    ESP_LOGD(TAG, "%s voice processing", enable ? "Enabling" : "Disabling");
    if (enable) {
        if (!audio_processor_initialized_) {
            audio_processor_->Initialize(codec_, OPUS_FRAME_DURATION_MS, models_list_);
            audio_processor_initialized_ = true;
        }

        /* We should make sure no audio is playing */
        ResetDecoder();
        audio_input_need_warmup_ = true;
        audio_processor_->Start();
        xEventGroupSetBits(event_group_, AS_EVENT_AUDIO_PROCESSOR_RUNNING);
    } else {
        audio_processor_->Stop();
        xEventGroupClearBits(event_group_, AS_EVENT_AUDIO_PROCESSOR_RUNNING);
    }
}

void AudioService::EnableAudioTesting(bool enable) {
    ESP_LOGI(TAG, "%s audio testing", enable ? "Enabling" : "Disabling");
    if (enable) {
        xEventGroupSetBits(event_group_, AS_EVENT_AUDIO_TESTING_RUNNING);
    } else {
        xEventGroupClearBits(event_group_, AS_EVENT_AUDIO_TESTING_RUNNING);
        /* Copy audio_testing_queue_ to audio_decode_queue_ */
        std::lock_guard<std::mutex> lock(audio_queue_mutex_);
        audio_decode_queue_ = std::move(audio_testing_queue_);
        audio_queue_cv_.notify_all();
    }
}

void AudioService::EnableDeviceAec(bool enable) {
    ESP_LOGI(TAG, "%s device AEC", enable ? "Enabling" : "Disabling");
    if (!audio_processor_initialized_) {
        audio_processor_->Initialize(codec_, OPUS_FRAME_DURATION_MS, models_list_);
        audio_processor_initialized_ = true;
    }

    audio_processor_->EnableDeviceAec(enable);
}

void AudioService::SetCallbacks(AudioServiceCallbacks& callbacks) {
    callbacks_ = callbacks;
}

void AudioService::PlaySound(const std::string_view& ogg) {
    if (!codec_->output_enabled()) {
        esp_timer_stop(audio_power_timer_);
        esp_timer_start_periodic(audio_power_timer_, AUDIO_POWER_CHECK_INTERVAL_MS * 1000);
        codec_->EnableOutput(true);
    }

    const uint8_t* buf = reinterpret_cast<const uint8_t*>(ogg.data());
    size_t size = ogg.size();
    size_t offset = 0;

    auto find_page = [&](size_t start)->size_t {
        for (size_t i = start; i + 4 <= size; ++i) {
            if (buf[i] == 'O' && buf[i+1] == 'g' && buf[i+2] == 'g' && buf[i+3] == 'S') return i;
        }
        return static_cast<size_t>(-1);
    };

    bool seen_head = false;
    bool seen_tags = false;
    int sample_rate = 16000; // 默认值

    while (true) {
        size_t pos = find_page(offset);
        if (pos == static_cast<size_t>(-1)) break;
        offset = pos;
        if (offset + 27 > size) break;

        const uint8_t* page = buf + offset;
        uint8_t page_segments = page[26];
        size_t seg_table_off = offset + 27;
        if (seg_table_off + page_segments > size) break;

        size_t body_size = 0;
        for (size_t i = 0; i < page_segments; ++i) body_size += page[27 + i];

        size_t body_off = seg_table_off + page_segments;
        if (body_off + body_size > size) break;

        // Parse packets using lacing
        size_t cur = body_off;
        size_t seg_idx = 0;
        while (seg_idx < page_segments) {
            size_t pkt_len = 0;
            size_t pkt_start = cur;
            bool continued = false;
            do {
                uint8_t l = page[27 + seg_idx++];
                pkt_len += l;
                cur += l;
                continued = (l == 255);
            } while (continued && seg_idx < page_segments);

            if (pkt_len == 0) continue;
            const uint8_t* pkt_ptr = buf + pkt_start;

            if (!seen_head) {
                // 解析OpusHead包
                if (pkt_len >= 19 && std::memcmp(pkt_ptr, "OpusHead", 8) == 0) {
                    seen_head = true;
                    
                    // OpusHead结构：[0-7] "OpusHead", [8] version, [9] channel_count, [10-11] pre_skip
                    // [12-15] input_sample_rate, [16-17] output_gain, [18] mapping_family
                    if (pkt_len >= 12) {
                        uint8_t version = pkt_ptr[8];
                        uint8_t channel_count = pkt_ptr[9];
                        
                        if (pkt_len >= 16) {
                            // 读取输入采样率 (little-endian)
                            sample_rate = pkt_ptr[12] | (pkt_ptr[13] << 8) | 
                                        (pkt_ptr[14] << 16) | (pkt_ptr[15] << 24);
                            ESP_LOGI(TAG, "OpusHead: version=%d, channels=%d, sample_rate=%d", 
                                   version, channel_count, sample_rate);
                        }
                    }
                }
                continue;
            }
            if (!seen_tags) {
                // Expect OpusTags in second packet
                if (pkt_len >= 8 && std::memcmp(pkt_ptr, "OpusTags", 8) == 0) {
                    seen_tags = true;
                }
                continue;
            }

            // Audio packet (Opus)
            auto packet = std::make_unique<AudioStreamPacket>();
            packet->sample_rate = sample_rate;
            packet->frame_duration = 60;
            packet->payload.resize(pkt_len);
            std::memcpy(packet->payload.data(), pkt_ptr, pkt_len);
            PushPacketToDecodeQueue(std::move(packet), true);
        }

        offset = body_off + body_size;
    }
}

bool AudioService::IsIdle() {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    return audio_encode_queue_.empty() && audio_decode_queue_.empty() && audio_playback_queue_.empty() && audio_testing_queue_.empty();
}

void AudioService::ResetDecoder() {
    std::lock_guard<std::mutex> lock(audio_queue_mutex_);
    opus_decoder_->ResetState();
    timestamp_queue_.clear();
    audio_decode_queue_.clear();
    audio_playback_queue_.clear();
    audio_testing_queue_.clear();
    audio_queue_cv_.notify_all();
}

void AudioService::CheckAndUpdateAudioPowerState() {
    auto now = std::chrono::steady_clock::now();
    auto input_elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - last_input_time_).count();
    auto output_elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - last_output_time_).count();
    if (input_elapsed > AUDIO_POWER_TIMEOUT_MS && codec_->input_enabled()) {
        codec_->EnableInput(false);
    }
    if (output_elapsed > AUDIO_POWER_TIMEOUT_MS && codec_->output_enabled()) {
        codec_->EnableOutput(false);
    }
    if (!codec_->input_enabled() && !codec_->output_enabled()) {
        esp_timer_stop(audio_power_timer_);
    }
}

void AudioService::SetModelsList(srmodel_list_t* models_list) {
    models_list_ = models_list;

#if CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32P4
    if (esp_srmodel_filter(models_list_, ESP_MN_PREFIX, NULL) != nullptr) {
        wake_word_ = std::make_unique<CustomWakeWord>();
    } else if (esp_srmodel_filter(models_list_, ESP_WN_PREFIX, NULL) != nullptr) {
        wake_word_ = std::make_unique<AfeWakeWord>();
    } else {
        wake_word_ = nullptr;
    }
#else
    if (esp_srmodel_filter(models_list_, ESP_WN_PREFIX, NULL) != nullptr) {
        wake_word_ = std::make_unique<EspWakeWord>();
    } else {
        wake_word_ = nullptr;
    }
#endif

    if (wake_word_) {
        wake_word_->OnWakeWordDetected([this](const std::string& wake_word) {
            if (callbacks_.on_wake_word_detected) {
                callbacks_.on_wake_word_detected(wake_word);
            }
        });
    }
}

bool AudioService::IsAfeWakeWord() {
#if CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32P4
    return wake_word_ != nullptr && dynamic_cast<AfeWakeWord*>(wake_word_.get()) != nullptr;
#else
    return false;
#endif
}

// ==================== 长音频播放功能实现 ====================

bool AudioService::StartLongAudioPlayback(uint32_t total_duration, int sample_rate) {
    if (long_audio_playing_) {
        ESP_LOGW(TAG, "长音频已在播放中");
        return false;
    }
    
    if (total_duration > LONG_AUDIO_MAX_DURATION_MS) {
        ESP_LOGW(TAG, "音频时长超过最大限制: %d > %d ms", total_duration, LONG_AUDIO_MAX_DURATION_MS);
        return false;
    }
    
    ESP_LOGI(TAG, "开始长音频播放: %d秒, 采样率: %d", total_duration / 1000, sample_rate);
    
    long_audio_playing_ = true;
    long_audio_total_duration_ = total_duration;
    long_audio_played_duration_ = 0;
    long_audio_start_time_ = std::chrono::steady_clock::now();
    
    // 调整缓冲区以适应长音频
    AdjustBufferSize(total_duration);
    
    // 创建长音频播放监控任务
    BaseType_t result = xTaskCreate([](void* param) {
        static_cast<AudioService*>(param)->LongAudioPlaybackTask();
    }, "long_audio_task", 4096, this, 3, &long_audio_task_handle_);
    
    if (result != pdPASS) {
        ESP_LOGE(TAG, "创建长音频播放任务失败");
        long_audio_playing_ = false;
        return false;
    }
    
    return true;
}

void AudioService::StopLongAudioPlayback() {
    if (!long_audio_playing_) {
        return;
    }
    
    ESP_LOGI(TAG, "停止长音频播放");
    long_audio_playing_ = false;
    long_audio_played_duration_ = 0;
    long_audio_total_duration_ = 0;
    
    // 等待任务结束
    if (long_audio_task_handle_ != nullptr) {
        vTaskDelete(long_audio_task_handle_);
        long_audio_task_handle_ = nullptr;
    }
}

float AudioService::GetLongAudioProgress() const {
    if (!long_audio_playing_ || long_audio_total_duration_ == 0) {
        return 0.0f;
    }
    
    return (float)long_audio_played_duration_ / long_audio_total_duration_ * 100.0f;
}

void AudioService::LongAudioPlaybackTask() {
    ESP_LOGI(TAG, "长音频播放监控任务启动");
    
    while (long_audio_playing_) {
        // 更新播放进度
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - long_audio_start_time_);
        long_audio_played_duration_ = elapsed.count();
        
        // 检查是否播放完成
        if (long_audio_played_duration_ >= long_audio_total_duration_) {
            ESP_LOGI(TAG, "长音频播放完成");
            StopLongAudioPlayback();
            break;
        }
        
        // 监控缓冲区状态
        {
            std::lock_guard<std::mutex> lock(audio_queue_mutex_);
            
            // 如果解码队列过满，记录警告
            if (audio_decode_queue_.size() > MAX_DECODE_PACKETS_IN_QUEUE * 0.9) {
                ESP_LOGW(TAG, "解码队列接近满载: %d/%d", 
                         audio_decode_queue_.size(), MAX_DECODE_PACKETS_IN_QUEUE);
            }
            
            // 如果播放队列过空，记录警告
            if (audio_playback_queue_.size() < MAX_PLAYBACK_TASKS_IN_QUEUE * 0.2) {
                ESP_LOGD(TAG, "播放队列较空: %d/%d", 
                         audio_playback_queue_.size(), MAX_PLAYBACK_TASKS_IN_QUEUE);
            }
        }
        
        // 每秒输出一次进度信息
        if (long_audio_played_duration_ % 5000 == 0) {
            float progress = GetLongAudioProgress();
            ESP_LOGI(TAG, "长音频播放进度: %.1f%% (%d/%d秒)", 
                     progress, long_audio_played_duration_ / 1000, long_audio_total_duration_ / 1000);
        }
        
        vTaskDelay(pdMS_TO_TICKS(100)); // 100ms检查间隔
    }
    
    ESP_LOGI(TAG, "长音频播放监控任务结束");
    long_audio_task_handle_ = nullptr;
    vTaskDelete(nullptr);
}

void AudioService::AdjustBufferSize(uint32_t required_duration) {
    uint32_t required_packets = required_duration / OPUS_FRAME_DURATION_MS;
    
    ESP_LOGI(TAG, "调整缓冲区大小，音频时长: %d秒, 需要包数: %d", 
             required_duration / 1000, required_packets);
    
    if (required_packets > MAX_DECODE_PACKETS_IN_QUEUE) {
        ESP_LOGI(TAG, "启用流式播放模式，超出标准缓冲区容量");
        
        // 清理现有队列，为长音频腾出内存
        std::lock_guard<std::mutex> lock(audio_queue_mutex_);
        
        // 保留必要的缓冲，清理多余数据
        while (audio_decode_queue_.size() > MAX_DECODE_PACKETS_IN_QUEUE / 4) {
            audio_decode_queue_.pop_front();
        }
        
        while (audio_playback_queue_.size() > MAX_PLAYBACK_TASKS_IN_QUEUE / 4) {
            audio_playback_queue_.pop_front();
        }
        
        ESP_LOGI(TAG, "内存优化完成，解码队列: %d, 播放队列: %d", 
                 audio_decode_queue_.size(), audio_playback_queue_.size());
    }
}
