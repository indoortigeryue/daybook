#!/bin/bash
# 一键重建干净 Flask 环境
# 使用系统自带 Python 而非 Anaconda

# Step 1: 删除旧环境
echo "🧹 Removing old virtual environment (if exists)..."
rm -rf env

# Step 2: 检查系统 Python 路径
SYS_PY=$(which python3)
echo "✅ Using Python at: $SYS_PY"

# Step 3: 创建新环境
echo "🐍 Creating new virtual environment..."
$SYS_PY -m venv env

# Step 4: 激活环境
echo "🚀 Activating environment..."
source env/bin/activate

# Step 5: 安装 Flask 相关包
echo "📦 Installing Flask and dependencies..."
pip install --upgrade pip
pip install Flask Flask-SQLAlchemy

# Step 6: 导出 requirements.txt
echo "📝 Freezing requirements..."
pip freeze > requirements.txt

# Step 7: 验证环境路径
echo "🔍 Current Python path:"
which python
which pip

# Step 8: 完成提示
echo "🎉 Environment setup complete!"
echo "📁 You can now run:"
echo "    source env/bin/activate"
echo "    python app.py"


# chmod +x reset_env.sh
# ./reset_env.sh