#!/bin/bash

# Bash script to prepare plant disease dataset
# Keeps 20% of images from each category and mixes them in one folder

SOURCE_PATH="${1:-./color}"
DEST_PATH="${2:-./mixed_images}"
KEEP_RATIO="${3:-0.20}"

echo -e "\033[0;32mStarting dataset preparation...\033[0m"
echo -e "\033[0;36mSource: $SOURCE_PATH\033[0m"
echo -e "\033[0;36mDestination: $DEST_PATH\033[0m"
echo -e "\033[0;36mKeep ratio: $(echo "$KEEP_RATIO * 100" | bc)%\033[0m"

# Create destination folder if it doesn't exist
if [ -d "$DEST_PATH" ]; then
    echo -e "\033[0;33mCleaning existing destination folder...\033[0m"
    rm -rf "$DEST_PATH"
fi
mkdir -p "$DEST_PATH"

total_images_copied=0
categories_processed=0

# Process each category directory
for category_path in "$SOURCE_PATH"/*/ ; do
    if [ ! -d "$category_path" ]; then
        continue
    fi
    
    category_name=$(basename "$category_path")
    echo -e "\n\033[0;33mProcessing category: $category_name\033[0m"
    
    # Count total images in this category
    total_images=$(find "$category_path" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l)
    
    if [ "$total_images" -eq 0 ]; then
        echo -e "  \033[0;90mNo images found, skipping...\033[0m"
        continue
    fi
    
    # Calculate number of images to keep (at least 1)
    images_to_keep=$(echo "scale=0; ($total_images * $KEEP_RATIO + 0.5) / 1" | bc)
    if [ "$images_to_keep" -lt 1 ]; then
        images_to_keep=1
    fi
    
    keep_percentage=$(echo "scale=1; ($images_to_keep / $total_images) * 100" | bc)
    
    echo -e "  \033[0;90mTotal images: $total_images\033[0m"
    echo -e "  \033[0;90mKeeping: $images_to_keep images (${keep_percentage}%)\033[0m"
    
    # Get all images and shuffle them, then take the first N
    category_prefix=$(echo "$category_name" | tr -cs '[:alnum:]' '_')
    image_index=1
    
    find "$category_path" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | \
        shuf -n "$images_to_keep" | \
        while IFS= read -r image_path; do
            image_name=$(basename "$image_path")
            new_filename="${category_prefix}_${image_index}_${image_name}"
            cp "$image_path" "$DEST_PATH/$new_filename"
            ((image_index++))
        done
    
    total_images_copied=$((total_images_copied + images_to_keep))
    categories_processed=$((categories_processed + 1))
    echo -e "  \033[0;32mCopied $images_to_keep images\033[0m"
done

echo -e "\n\033[0;32m================================\033[0m"
echo -e "\033[0;32mDataset preparation complete!\033[0m"
echo -e "\033[0;36mCategories processed: $categories_processed\033[0m"
echo -e "\033[0;36mTotal images copied: $total_images_copied\033[0m"
echo -e "\033[0;36mDestination: $DEST_PATH\033[0m"
echo -e "\033[0;32m================================\033[0m"
