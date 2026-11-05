# ICU 课程封面

通过内置 `image_gen` 绘制，采用统一的医学线描插画、哑光色块与轻微纸感。课程标题使用 LearnHouse 原生网页文字，图片不生成标题、标志或医学数值。图像为课程主题的装饰性插画，不作诊疗操作图示。

最终上传文件均保存在本目录，1279 × 720 WebP；原始生成 PNG 保留在操作机的 Codex 生成目录。最终完整提示词由 [prompts.json](prompts.json) 的公共提示词和各主题描述组合；两处经审阅的编辑提示词也保存在该文件中。

| 文件 | 对应课程 |
| --- | --- |
| [platform.webp](platform.webp) | 平台使用与培训须知 |
| [handover.webp](handover.webp) | ICU入科与规范交接班 |
| [ventilation.webp](ventilation.webp) | 气道管理与机械通气 |
| [circulation.webp](circulation.webp) | 休克与血流动力学 |
| [infection.webp](infection.webp) | 感染与脓毒症 |
| [sedation.webp](sedation.webp) | 镇痛镇静、谵妄与早期康复 |
| [renal.webp](renal.webp) | AKI、CRRT与内环境 |
| [nutrition.webp](nutrition.webp) | 营养与常见系统问题 |
| [resuscitation.webp](resuscitation.webp) | 抢救技能与护理配合 |
| [cases.webp](cases.webp) | 病例讨论与教学考核 |
| [admin.webp](admin.webp) | 管理员工作台与交接手册 |
| [examples.webp](examples.webp) | ICU教学示例：交接班、病例表达与文献阅读 |

`upload_covers.py` 通过原生缩略图 API 附加到课程，私有状态文件保留此前封面字段及本次文件摘要。课程的 public/published 状态均保持原值，未借封面上传发布草稿。
