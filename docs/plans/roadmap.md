<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-08-09 19:43:11

[~][X+] 1. ZQuant
├── [x][Y+] 1-7. M1: 活筹指数数据链打通
│   ├── [x][Y+] 1-7-7. TDX .day 解析器验证
│   ├── [x][Y+] 1-7-8. SQLite 建表+CRUD
│   ├── [x][Y+] 1-7-9. TUI 活筹回填面板
│   ├── [x][Y+] 1-7-10. 活筹信号计算+多空判定
│   ├── [x][Y+] 1-7-11. CLI status 命令
│   └── [x][Y+] 1-7-12. M1 端到端验证
├── [x][X+] 1-8. M2: B系列买点信号
│   ├── [x][Y+] 1-8-1. MA+量比指标计算
│   ├── [x][Y+] 1-8-2. KDJ 指标计算
│   ├── [x][Y+] 1-8-3. B1/B2/B3 信号检测
│   ├── [x][Y+] 1-8-4. scan CLI 命令+结果输出
│   ├── [x][Y+] 1-8-5. M2 端到端验证
│   └── [x][Y+] 1-8-6. TDX 全市场股票枚举
├── [x][X+] 1-9. M3: S系列卖点+滴滴风控
│   ├── [x][Y+] 1-9-1. S1/S2/S3 卖点信号检测
│   ├── [x][Y+] 1-9-2. 滴滴风控信号
│   ├── [x][Y+] 1-9-3. scan CLI 集成S信号
│   └── [x][Y+] 1-9-4. M3 端到端验证
├── [x][X+] 1-10. M4: 仓位量化框架
├── [x][X+] 1-11. M5: 回测引擎
├── [x][X+] 1-12. M6: TUI完整面板
└── [~][X+] 1-13. M7: 多端界面(Reflex)
    ├── [x][X+] 1-13-1. P0: 薄FastAPI API层
    ├── [x][X+] 1-13-2. P1: Flet骨架(四页导航)
    ├── [x][X+] 1-13-3. P2: 可视化落地(flet-charts)
    ├── [x][X+] 1-13-4. P3: 多端打包+agent验证
    ├── [ ][X+] 1-13-5. Reflex 依赖接入+骨架初始化
    ├── [ ][X+] 1-13-6. 四页界面移植(概览/扫描/仓位/回测)
    ├── [ ][X+] 1-13-7. 图表落地(Reflex组件)
    └── [ ][X+] 1-13-8. agent-browser 验证+响应式适配

### 当前施工：1-13. M7: 多端界面(Reflex)

目标不变(PC/Web/手机一套代码); 技术方案从Flet调整; 纯HTML+JS单页已验证可行(web/index.html)

**决策：**
- Q: M7 技术方案(Flet web)状态? → 已弃用 (Flet 0.86.5 web 渲染有不可修复 bug(scene-host/canvas=0, 官方示例也灰色); 0.85.3 与 flet-charts 不兼容)
- Q: 新方案调研方向? → GitHub 高stars 跨端框架 + Agent-Coding readiness (候选: Flet/NiceGUI/Streamlit/Gradio/Reflex/Textual/Tauri/Electron/Capacitor; 实时stars已查)
- Q: 调研发现(Agent-Coding维度)? → NiceGUI结构清晰AI理解快; Reflex纯Python编译前端LLM集成好(实测20分钟95%需求); Gradio样式层冲突AI易出错; Streamlit改样式费劲 (来源: InfoQ 2026选型 + LinkedIn实测(Claude Opus 4.5))
- Q: M7 新技术方案? → Reflex(纯Python全栈, AI生成体验冠军) (28.8k⭐; 纯Python编译前端; LLM实测20分钟95%需求; 与现有FastAPI API层共存)
- Q: Reflex 接入方式? → C: 全栈接管, API层废弃 (Reflex直接import core; FastAPI API层退役; 纯HTML+JS(web/index.html)被Reflex取代)
- Q: 过渡策略? → Reflex优先, API+web保留不删 (分阶段: Reflex先行验证, 通过后再清理api/web; 改动严格分离)
- Q: Reflex 版本? → 锁定 0.9.8 (2026-08-04发布唯一正式版; Python3.13兼容; 避开0.8.x Open Redirect漏洞(CVE范围<=0.8.14))

**当前子树：**
├── [x][X+] 1-13-1. P0: 薄FastAPI API层
├── [x][X+] 1-13-2. P1: Flet骨架(四页导航)
├── [x][X+] 1-13-3. P2: 可视化落地(flet-charts)
├── [x][X+] 1-13-4. P3: 多端打包+agent验证
├── [ ][X+] 1-13-5. Reflex 依赖接入+骨架初始化
├── [ ][X+] 1-13-6. 四页界面移植(概览/扫描/仓位/回测)
├── [ ][X+] 1-13-7. 图表落地(Reflex组件)
└── [ ][X+] 1-13-8. agent-browser 验证+响应式适配
<!-- ROADMAP_SECTION_END -->
