# 批量清单格式

`scripts/render_album.py` 接收 UTF-8 JSON 清单。示例：

```json
{
  "source_dir": "E:/DCIM/102_FUJI/未处理",
  "output_dir": "D:/GPT文件/outputs/今日小红书整套方案",
  "signature": "RUYAO JINGHONG",
  "albums": [
    {
      "folder": "01-宋人喝茶为何如此高雅-祥云壶",
      "prefix": "全手工刻绘，祥云壶",
      "kicker": "宋人茶事｜秩序",
      "post_title": "为什么宋人喝茶，也那么高雅？",
      "post_body": "完整正文……",
      "hashtags": ["宋人茶事", "汝瓷", "京鸿汝窑"],
      "sources": [
        {"label": "故宫博物院｜宋代茶具", "url": "https://www.dpm.org.cn/"}
      ],
      "pages": [
        {"title": "为什么宋人喝茶，也那么高雅？", "subtitle": "他们喝的不只是茶\n而是一整套有秩序的生活"},
        {"title": "宋代茶事，讲究到什么程度？", "subtitle": "从碾茶、罗茶到候汤、点茶"}
      ]
    }
  ]
}
```

## 规则

- `prefix` 匹配源目录中以该文字开头的 JPG/JPEG/PNG 文件；文件按括号中的自然序号排序。
- `pages` 数量必须与匹配照片数量完全一致，脚本遇到不一致时停止，不静默丢图。
- `folder` 是输出子目录名。
- `kicker` 是图片顶部的小栏目名。
- `post_body`、`hashtags`、`sources` 会写入每套 `小红书文案与逐页文字.md`。
- `signature` 缺省为 `RUYAO JINGHONG`。

输出结构：

```text
output_dir/
|-- 00-成品封面总览.jpg
|-- 00-交付说明.md
`-- 01-主题-器物/
    |-- images/
    |   |-- 01-标题.jpg
    |   `-- ...
    |-- 01-主题-器物-图册总览.jpg
    `-- 小红书文案与逐页文字.md
```
