# 她自己的笔记本（astrbot_plugin_notes）

> 一个**完全独立**的成长型知识插件：让角色把查到的结论记下来，下次遇到相关话题自动带上，并且知道每条信息来源可不可信。

不依赖、不修改任何其它插件。删掉目录就等于卸载，数据在自己的数据目录里。

---

## 它解决什么问题

角色能记住“昨天聊过什么”，不等于能答对“那个东西叫什么”。

| | 对话记忆插件 | 本插件 |
|---|---|---|
| 内容 | 聊天摘要、关系、情绪 | 事实、数值、结论 |
| 来源 | 对话本身 | 搜索 / 网页 / 她自己查到的 |
| 形态 | 图谱 + 摘要 | 一条条带来源的笔记 |
| 回答的问题 | “她还记得我吗” | “她答得对吗” |

分开做的好处：可以单独关掉、单独备份、单独发版，出问题不影响陪伴链路。

---

## 安装

1. 把整个 `astrbot_plugin_notes/` 目录放进 `data/plugins/`
2. 重启 AstrBot（或面板里重载插件）
3. 面板 → 插件管理 → 她自己的笔记本，按需调配置

**卸载**：删掉目录即可。数据在 `data/plugin_data/astrbot_plugin_notes/`，要不要一起删自己决定。

---

## 它怎么工作

三个模型工具（自动出现在工具列表里）：

| 工具 | 作用 | 什么时候用 |
|---|---|---|
| `notes_search` | 查自己的笔记本 | 回答具体事实、数据、人名之前，先看以前记过没 |
| `notes_write` | 写一条笔记 | 查到了稳定结论，以后还会用到 |
| `notes_fetch` | 抓网页正文 | 需要核对细节，或搜索结果只有标题没有内容 |

一次典型的成长过程：

```
用户问：那个东西具体怎么用？
  → notes_search 查自己记过没
  → 没记过，联网搜索
  → notes_fetch 打开最靠谱的一页看正文
  → 判断哪些是稳定结论，notes_write 记下来（带来源）
  → 下次再问，notes_search 直接命中，不用重搜
```

管理命令（你自己用）：

```
笔记                看统计
笔记 搜索 关键词     搜笔记
笔记 删除 3f2a1b9c   删一条
笔记 导出            导出成 notes_export.json
```

---

## 面板页（管理笔记本）

面板 → 插件管理 → **她自己的笔记本** → 打开「笔记本」页。

| 功能 | 说明 |
|---|---|
| 统计 | 总数、可信 / 一般 / 存疑分布、被引用次数 |
| 列表 | 按更新时间倒序，显示可信度、来源、命中次数 |
| 搜索 | 标题 / 正文 / 标签，前端即时过滤，支持 `Ctrl/⌘ + K` |
| 新建 / 编辑 | 标题、正文、来源、标签；来源填了会按域名自动分级 |
| 删除 | 二次确认 |
| 导入 | 选 `.json` / `.md` / `.txt`，按格式自动解析成多条 |
| 导出 | 下载当前全部笔记的 JSON |

**导入格式**

* JSON：`[{"title":"…","body":"…","source":"…","tags":["…"]}]`，也接受单个对象
* Markdown：按 `#` / `##` 标题切块，标题即笔记标题
* 纯文本：整篇作为一条，标题取文件名

**面板后端接口**

插件注册的路由前缀是 `/<插件名>`，面板桥接会拼成 `/api/plug/<插件名>/<endpoint>`：

| 方法 | 实际路径 | endpoint | 说明 |
|---|---|---|---|
| GET | `/api/plug/astrbot_plugin_notes/list` | `list` | 全部笔记 + 统计 |
| GET | `/api/plug/astrbot_plugin_notes/stats` | `stats` | 统计 |
| POST | `/api/plug/astrbot_plugin_notes/save` | `save` | 带 `id` 更新，不带新增 |
| POST | `/api/plug/astrbot_plugin_notes/delete` | `delete` | `{"id": "..."}` |
| POST | `/api/plug/astrbot_plugin_notes/import` | `import` | `{"name": "...", "content": <string\|list>}` |

页面通过 `AstrBotPluginPage` 桥调用（`bridge.apiGet("list")`），鉴权由面板统一处理，插件自己不碰 token。

> 两个踩过的坑：桥脚本由面板注入在 HTML 末尾，可能晚于页面内联脚本执行，要轮询等待 `window.AstrBotPluginPage`；endpoint 必须是不带前导斜杠的相对路径。

---

## 配置

| 键 | 默认 | 说明 |
|---|---|---|
| `enabled` | true | 总开关，关掉后工具和注入都不生效，数据保留 |
| `inject_enabled` | true | 对话时是否自动带上相关笔记 |
| `inject_limit` | 2 | 每轮最多注入几条（1-5） |
| `min_score` | 1.0 | 命中阈值，越高越保守 |
| `fetch_enabled` | true | 是否允许抓网页 |
| `fetch_timeout` | 20 | 抓取超时（秒） |
| `fetch_max_chars` | 6000 | 单页最多返回多少字符 |
| `wiki_domains` | huijiwiki.com,fandom.com,… | 这些域名标为「可信」 |
| `guide_domains` | bilibili.com,nga.cn,… | 这些标为「一般」，其余「存疑」 |

注入时长这样：

```
【你笔记本里查到的东西（你自己以前记的）】
- 某个机制的要点（可信｜https://example-wiki.com/...）：先做 A 再做 B，A 有冷却…
标「存疑」的别当定论，可以说得保守一点。
```

**这就是“自己判断对错”的落点**：来源分级不是替她下结论，而是给她一个可信度标签，由她决定回答时说得多笃定。

---

## 数据格式

`data/plugin_data/astrbot_plugin_notes/notes.jsonl`，一行一条：

```json
{"id":"3f2a1b9c","title":"某个机制的要点","body":"先做 A 再做 B…","source":"https://example.com/page","trust":"high","tags":["示例"],"created_at":1792400000.0,"updated_at":1792400000.0,"hits":3}
```

* 写入用临时文件 + `os.replace`，写一半崩了不会毁掉旧库
* 读取时坏行直接跳过，不会整个库读不出来
* 同 `source` 再写会覆盖旧内容，方便她更新

---

## 设计取舍

**为什么不用向量库？**
笔记量级预计几百条，字符二元组倒排已经够快，不依赖 embedding 供应商，也不多一个失败点。真到几千条，只需要替换 `store.py` 的 `search()`。

**为什么不分词？**
中文分词要装依赖，二元组命中率够用，还能容忍错字（“雷横默”/“横默”都能命中）。

**为什么抓网页不顺手摘要？**
插件里再调一次模型，会让 token 花在哪儿变得不可控，也把模型选择绑死。现在插件只取回正文，**判断和提炼交给对话模型自己**——她能决定哪些值得记，这才叫成长。

---

## 扩展

* 加检索能力：改 `store.py` 的 `search()`
* 加来源分级规则：改 `main.py` 的 `trust_of()`
* 加新工具：在 `tools.py` 写一个 `FunctionTool` 子类，在 `main.py` 的 `self.tools` 里追加
* 换存储：`store.py` 只暴露 `add / update / delete / search / all / stats`，换 SQLite 不影响上层

---

## 发布到插件市场

参考官方文档：[发布插件到插件市场](https://docs.astrbot.app/dev/star/plugin-publish.html)

1. **建 GitHub 仓库**，把本目录的内容放到仓库根目录（不是再套一层）
2. 填 `metadata.yaml` 的 `repo:`（当前是空字符串，发布前必须填）
3. 清理不该进仓库的东西：`__pycache__/`、`.venv/`、本地数据（`.gitignore` 已备好）
4. 去 [AstrBot 插件发布页](https://cloud.astrbot.app/publish) 注册 AstrBot Cloud 账号并提交仓库
5. 打包体积上限 **16MB**，本插件源码只有几十 KB，无需处理资源

发布前检查：

* `metadata.yaml` 的 `version` 与 README 一致
* 没有硬编码本地路径、没有 `from astrbot_plugin_xxx import ...`
* 在干净环境里能只靠本目录启动（不依赖其它插件）

---

## 已知边界

* 检索是关键词匹配，不是语义匹配：“怎么打这个 boss” 搜不到 “这个 boss 的打法”
* 抓取只处理 HTML，不执行 JS，动态渲染的页面可能只能拿到空壳
* 没有跨用户隔离：所有会话共用一本笔记（陪伴场景下通常正是想要的）
