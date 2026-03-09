#!/usr/bin/env python3
"""
设置Opus库DLL路径
在导入任何使用opuslib的模块之前调用此函数
"""

import os
import sys

def setup_opus_dll():
    """设置Opus DLL搜索路径"""
    if os.name == 'nt':  # Windows系统
        # 获取项目根目录
        project_root = os.path.dirname(os.path.abspath(__file__))
        opus_dll_path = os.path.join(project_root, 'opus.dll')
        
        if os.path.exists(opus_dll_path):
            # 方法1: 使用add_dll_directory (Python 3.8+)
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(project_root)
                    print(f"✅ 已添加DLL搜索路径: {project_root}")
                except Exception as e:
                    print(f"❌ 添加DLL搜索路径失败: {e}")
            
            # 方法2: 设置PATH环境变量 (兼容性更好)
            current_path = os.environ.get('PATH', '')
            if project_root not in current_path:
                os.environ['PATH'] = project_root + os.pathsep + current_path
                print(f"✅ 已设置PATH环境变量: {project_root}")
            
            # 方法3: 将DLL路径添加到sys.path (最后的备选方案)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
                print(f"✅ 已添加到sys.path: {project_root}")
                
            return True
        else:
            print(f"❌ 未找到opus.dll: {opus_dll_path}")
            return False
    
    return True  # 非Windows系统直接返回True

def test_opus_after_setup():
    """设置后测试Opus功能"""
    try:
        import opuslib
        print("✅ opuslib导入成功")
        
        # 测试编码器
        encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)
        print("✅ Opus编码器创建成功")
        
        # 测试编码
        import struct
        frame_size = 960
        test_pcm = struct.pack('<' + 'h' * frame_size, *([0] * frame_size))
        opus_data = encoder.encode(test_pcm, frame_size)
        
        if opus_data and len(opus_data) > 0:
            print(f"✅ Opus编码测试成功: {len(opus_data)}字节")
            return True
        else:
            print("❌ Opus编码返回空数据")
            return False
            
    except Exception as e:
        print(f"❌ Opus测试失败: {e}")
        return False

if __name__ == "__main__":
    print("🎵 设置Opus库DLL路径...")
    setup_success = setup_opus_dll()
    
    if setup_success:
        print("\n🧪 测试Opus功能...")
        test_success = test_opus_after_setup()
        
        if test_success:
            print("\n🎉 Opus库设置成功！")
        else:
            print("\n⚠️ Opus库设置可能有问题")
    else:
        print("\n❌ Opus库设置失败")
