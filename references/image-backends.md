# 生图后端

## Codex 内置生图（默认）

当前工具能显式选择 **Images 2.6** 时选用它。工具只有通用生图入口时，使用该入口并检查返回的模型信息。工具未确认时，逐图记录「Codex 内置生图，具体模型未确认」。模型名不作为 API 模型 ID 推断。使用环境提供的 imagegen 技能，并按逐图提示词分别生成。等待结果落到项目文件夹后核对图文。工具不可用时按下方规则回退。

## 用户自配 API（显式启用）

仅在用户选择第三方 API 并指定服务时使用。需要 API 基址或完整生图端点、服务商模型 ID 和 bearer 密钥对应的环境变量名。只读取指定的密钥变量。不要把密钥写进调用参数、仓库、日志、提示词或成品 Markdown。给服务发送已去标识的单张图提示词，不传原报告或个人信息。使用临时 UTF-8 文本文件保存准确的请求文本。

脚本使用 Python 3 标准库。API 基址应包含供应商要求的版本前缀，例如 /v1。脚本通过 POST 调用 /images/generations，支持单图返回的 b64_json 或公开 HTTPS 图片 URL。下载 URL 时不会转发 API 密钥。优先使用返回 PNG 的配置。将密钥保存在当前 Harness 可见的环境变量中。

    python3 /path/to/docx2latex/scripts/generate_image.py \
      --endpoint https://images.example.com/v1 \
      --model provider-image-model --key-env DOCX2LATEX_IMAGE_API_KEY \
      --prompt-file /path/to/work/frame-06-prompt.txt \
      --output '/path/to/project/figures/Frame 06-整体技术路线.png'

供应商支持具体尺寸时可传 --size，如 1536x1024。生成结果必须与文件后缀一致。WebP 在引入 XeLaTeX 前转换成 PNG 或 JPEG。脚本返回请求模型 ID 和回包中报告的模型。保存实际提示词及可确认的模型，回包未提供模型时标注「实际模型未独立确认」。不要用成功请求推断服务商内部模型。

## 回退

所选方式不可用、密钥缺失、请求失败或生成图无法准确表达科研关系时，继续用 TikZ 或等效绘图工具完成图片，并记录「TikZ 绘制」或实际采用的方式。单次调用出现结果不明的网络错误时不自动重发，避免重复计费。逐图记录实际交付图的生成方式。
