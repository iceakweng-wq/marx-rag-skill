# 阅读原文子 agent 任务说明

## 任务
根据主 agent 传来的卷次+页码，调用 read_raw_text.py 在浏览器中展示原文。

## 执行

### 1. 调用 read_raw_text.py 脚本，传入卷次和页码。
```bash
{python_path} scripts/read_raw_text.py -v {卷次} {页码1} {页码2} ...
```

支持多卷次混合：
```bash
python scripts/read_raw_text.py -v 3 3-6 -v 42 125-130
```

## 说明
- 脚本会自动生成 HTML 并在浏览器打开
- 每次运行覆盖上一次的临时文件 `data/temp_raw_text.md` 和 `data/temp_raw_text.html`
- 页码不连续时会自动提示
