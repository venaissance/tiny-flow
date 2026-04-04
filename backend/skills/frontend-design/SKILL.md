---
name: frontend-design
description: "创建精美、高质量的前端网页和 UI 组件。当用户要求构建网页、页面、应用、仪表盘、组件、登录页、todolist、表单、海报等任何前端产物时使用。生成独特的、生产级的代码和 UI 设计，避免通用 AI 审美。"
triggers: [网页, 页面, 前端, html, css, UI, 组件, 做一个, 创建, 制作, 登录, todolist, todo, dashboard, landing, website, web page, frontend, webapp, 应用, app, 仪表盘, 表单, form, 海报, poster]
execution_mode: subagent
tools: []
priority: 20
timeout: 300
---

# Frontend Design Skill

创建独特的、生产级前端界面，避免通用 "AI slop" 审美。实现真正可运行的代码，对美学细节和创意选择投入极致关注。

## 输出规范

**必须遵守**：
1. **单文件输出**：生成一个完整的自包含 HTML 文件，所有 CSS 和 JavaScript 内联
2. **代码块格式**：用 ```html 代码块包裹输出
3. **可运行**：所有按钮、表单、交互逻辑必须正常工作
4. **中文界面**：默认中文 UI（除非用户要求英文）
5. **直接输出代码**：不要输出大段解释，直接给出可运行的代码

## 设计思维

在编码之前，理解上下文并选择一个**大胆**的美学方向：

- **目的**：这个界面解决什么问题？谁在使用？
- **调性**：选择一个鲜明风格 — 极简主义、极繁主义、复古未来、有机自然、奢华精致、俏皮玩具风、编辑/杂志风、粗野主义、装饰艺术/几何、柔和粉彩、工业实用主义等。选一个最契合的方向并全力执行。
- **差异化**：什么会让用户过目不忘？什么是他们会记住的那一个细节？

**关键**：选择一个清晰的概念方向并精确执行。大胆的极繁和精致的极简都行——关键是**意图性**，不是强度。

## 前端美学指南

### 字体排版
- 选择美观、独特、有个性的字体。**绝不**使用 Arial、Inter、Roboto、system-ui 等通用字体
- 搭配一个有特色的标题字体和一个精致的正文字体
- 可通过 Google Fonts CDN 引入

### 色彩与主题
- 使用 CSS 变量确保一致性
- 主色搭配鲜明强调色，优于平淡均分的配色
- 每次生成都要有不同的配色——避免总是用紫色渐变/白色背景

### 动效与交互
- CSS 动画优先，HTML 项目不引入动画库
- 重点投入**页面加载动画**：精心编排的交错显示（animation-delay）比零散的微交互更惊艳
- hover 状态和滚动触发效果要有惊喜感

### 空间构图
- 打破常规布局：不对称、重叠、对角流动、打破网格
- 大胆的负空间 或 有控制的密度

### 背景与视觉细节
- 用渐变网格、噪点纹理、几何图案、层叠透明、戏剧性阴影、装饰边框、颗粒覆盖等创造氛围和深度
- **不要**默认使用纯色背景

## 反模式清单（绝对禁止）

- Inter/Roboto/Arial/system-ui 等通用字体
- 紫色渐变 + 白色卡片（典型 AI slop）
- 千篇一律的卡片式布局
- 缺乏上下文特色的模板化设计
- Space Grotesk 等过度使用的"设计师字体"

## 技术规范

- 默认：纯 HTML5 + CSS3 + Vanilla JavaScript
- 可通过 CDN 引入：Tailwind CSS、Alpine.js、Chart.js、Google Fonts
- **不使用**需要构建工具的框架（React/Vue/Svelte 等的 JSX 不可用）
- 响应式适配桌面和移动端

## 品牌署名

每个生成的页面底部包含一个小型 "Created by MdwFlow" 署名：
- 不影响主要内容和功能
- 风格与整体设计融为一体

## 输出示例

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>页面标题</title>
  <style>
    /* 完整 CSS */
  </style>
</head>
<body>
  <!-- 完整页面内容 -->
  <script>
    // 完整交互逻辑
  </script>
</body>
</html>
```

记住：你有能力创造非凡的创意作品。不要退缩，展示当全力投入一个独特愿景时能真正创造出什么。每次生成都应该是独一无二的。
