# 睡前故事功能 API 文档

## 概述

睡前故事功能为青少年用户提供个性化的睡前故事服务，支持精选故事和AI创作故事两种模式。

## WebSocket 消息接口

### 1. 获取故事类型选项

**消息类型**: `get_story_types`

**请求参数**: 无

**响应消息**: `story_types`

**响应数据**:
```json
{
  "types": [
    {
      "type": "preset",
      "name": "精选故事",
      "description": "精心挑选的经典睡前故事",
      "icon": "📚"
    },
    {
      "type": "generated",
      "name": "创作新故事", 
      "description": "根据你的喜好创作全新故事",
      "icon": "✨"
    }
  ]
}
```

### 2. 获取故事主题列表

**消息类型**: `get_story_themes`

**请求参数**: 无

**响应消息**: `story_themes`

**响应数据**:
```json
{
  "themes": [
    {
      "name": "智慧的寓言",
      "description": "富有哲理的小故事，启发思考",
      "suitable_characters": ["xiaozhi", "xiaonuan"]
    },
    {
      "name": "思考的旅程",
      "description": "引导深入思考的成长故事",
      "suitable_characters": ["xiaozhi", "xiaocheng"]
    },
    {
      "name": "古老的传说",
      "description": "神秘而富有文化底蕴的传说故事",
      "suitable_characters": ["xiaozhi", "xiaoshu"]
    },
    {
      "name": "哲理的故事",
      "description": "蕴含人生道理的温暖故事",
      "suitable_characters": ["xiaozhi", "xiaonuan"]
    },
    {
      "name": "成长的启示",
      "description": "关于成长和自我发现的故事",
      "suitable_characters": ["xiaocheng", "xiaonuan"]
    }
  ]
}
```

### 3. 获取智能故事推荐

**消息类型**: `get_story_recommendation`

**请求参数**:
```json
{
  "mood": "happy"  // 可选，用户当前情绪
}
```

**响应消息**: `story_recommendation`

**响应数据**:
```json
{
  "recommended_theme": "成长的启示",
  "theme_description": "关于成长和自我发现的故事",
  "character_name": "小智",
  "reason": "你现在心情不错，来听个轻松愉快的故事吧！",
  "suitable_story_type": "generated"
}
```

### 4. 获取睡前故事（主要功能）

**消息类型**: `get_bedtime_story`

**请求参数**:
```json
{
  "story_type": "preset",     // "preset" 或 "generated"
  "theme": "智慧的寓言"       // 可选，故事主题
}
```

**响应消息**: `bedtime_story`

**响应数据**:
```json
{
  "story": {
    "title": "种子的智慧",
    "content": "从前有一颗小种子...",
    "character_id": "xiaozhi",
    "character_name": "小智",
    "character_style": "富有哲理、引人思考、启发智慧的故事",
    "type": "preset",           // "preset" 或 "generated"
    "theme": "智慧的寓言",      // 如果是生成的故事
    "created_at": "2025-11-14T09:19:40.123456",
    "user_id": "user123"
  },
  "request_params": {
    "story_type": "preset",
    "theme": "智慧的寓言",
    "character_id": "xiaozhi"
  }
}
```

### 5. 再听一遍故事

**消息类型**: `repeat_story`

**请求参数**:
```json
{
  "last_story": {
    // 上一个故事的完整数据
  }
}
```

**响应消息**: `bedtime_story`

**响应数据**:
```json
{
  "story": {
    // 相同的故事数据
  },
  "is_repeat": true
}
```

### 6. 换一个故事

**消息类型**: `change_story`

**请求参数**:
```json
{
  "story_type": "preset",     // 保持相同的类型
  "theme": "智慧的寓言"       // 保持相同的主题
}
```

**响应消息**: `bedtime_story`

**响应数据**:
```json
{
  "story": {
    // 新的故事数据
  },
  "is_new": true,
  "request_params": {
    "story_type": "preset",
    "theme": "智慧的寓言",
    "character_id": "xiaozhi"
  }
}
```

## 角色配置

系统支持4个角色，每个角色有不同的讲故事风格：

| 角色ID | 角色名 | 风格特点 |
|--------|--------|----------|
| xiaonuan | 小暖 | 温柔、治愈、充满温暖和希望的故事 |
| xiaocheng | 小橙 | 轻松、有趣、充满正能量和惊喜的故事 |
| xiaozhi | 小智 | 富有哲理、引人思考、启发智慧的故事 |
| xiaoshu | 小树 | 平静、简洁、让人放松和安心的故事 |

## 情绪推荐映射

系统会根据用户当前情绪智能推荐合适的故事主题：

| 情绪 | 推荐主题 | 推荐理由 |
|------|----------|----------|
| happy | 成长的启示、思考的旅程 | 心情不错，适合听轻松愉快的故事 |
| sad | 哲理的故事、智慧的寓言 | 温暖的故事能让人感觉好一些 |
| anxious | 古老的传说、哲理的故事 | 能让人放松的故事 |
| tired | 智慧的寓言、哲理的故事 | 听听能放松的故事 |
| excited | 思考的旅程、成长的启示 | 一起经历冒险 |
| calm | 古老的传说、智慧的寓言 | 适合平静时听的故事 |

## 错误处理

所有接口在出错时会返回统一的错误消息：

**响应消息**: `error`

**响应数据**:
```json
{
  "message": "错误描述"
}
```

常见错误：
- "获取故事类型失败"
- "获取故事主题失败" 
- "获取故事推荐失败"
- "获取睡前故事失败"
- "没有找到上一个故事"
- "重复播放故事失败"
- "更换故事失败"

## 使用流程示例

### 典型的睡前故事使用流程：

1. **获取故事选项**
   ```javascript
   // 获取故事类型
   websocket.send(JSON.stringify({
     type: "get_story_types"
   }));
   
   // 获取故事主题
   websocket.send(JSON.stringify({
     type: "get_story_themes"
   }));
   ```

2. **获取智能推荐**（可选）
   ```javascript
   websocket.send(JSON.stringify({
     type: "get_story_recommendation",
     mood: "happy"
   }));
   ```

3. **获取睡前故事**
   ```javascript
   websocket.send(JSON.stringify({
     type: "get_bedtime_story",
     story_type: "generated",
     theme: "智慧的寓言"
   }));
   ```

4. **再听一遍或换一个**
   ```javascript
   // 再听一遍
   websocket.send(JSON.stringify({
     type: "repeat_story",
     last_story: lastStoryData
   }));
   
   // 换一个故事
   websocket.send(JSON.stringify({
     type: "change_story",
     story_type: "generated",
     theme: "智慧的寓言"
   }));
   ```

## 注意事项

1. **用户认证**: 所有接口都需要用户已登录
2. **角色依赖**: 故事会根据用户当前选择的角色来调整风格
3. **降级机制**: 如果AI生成故事失败，会自动降级为预设故事
4. **缓存优化**: 预设故事支持缓存，响应更快
5. **个性化**: 生成的故事会包含用户昵称，增加代入感
