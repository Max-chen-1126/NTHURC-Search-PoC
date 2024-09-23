#!/bin/bash

# 設置源目錄和目標目錄
SOURCE_DIR="/Users/mai/Downloads/新北住都中心提供ㄧ名承辦之錄音檔"
TARGET_DIR="/Users/mai/Downloads/新北住都中心提供ㄧ名承辦之錄音檔_converted"

# 創建目標目錄（如果不存在）
mkdir -p "$TARGET_DIR"

# 遍歷源目錄中的所有 WAV 文件（包括子目錄）
find "$SOURCE_DIR" -type f -name "*.wav" | while read -r file; do
    # 獲取相對路徑
    rel_path=${file#$SOURCE_DIR/}
    # 創建目標文件的目錄
    target_dir="$TARGET_DIR/$(dirname "$rel_path")"
    mkdir -p "$target_dir"
    # 設置目標文件名
    target_file="$target_dir/$(basename "${file%.*}")_linear16.wav"
    
    echo "Converting $file to $target_file"
    
    # 使用 ffmpeg 進行轉換
    ffmpeg -i "$file" -acodec pcm_s16le -ar 8000 -ac 1 "$target_file"
done

echo "Conversion complete. Converted files are in $TARGET_DIR"