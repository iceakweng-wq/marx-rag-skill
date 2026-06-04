# 阅读原文要求

## 任务
根据卷次+页码，调用 read_raw_text.py 在浏览器中展示原文。

## 执行
使用例子：
```bash
# 单卷次（卷次数字即可，不用加 v 前缀；页码直接用数字）
{python_path} scripts/read_raw_text.py -v 42 128 129 130

# 页码范围（用 - 连接）
{python_path} scripts/read_raw_text.py -v 23 100-105

# 多卷次混合
{python_path} scripts/read_raw_text.py -v 3 3-6 48-51 -v 42 125-130 167-170
```

脚本会自动生成 HTML 并打开浏览器。每次运行覆盖临时文件，不留痕迹。
