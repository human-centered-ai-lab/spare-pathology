# Dataset format

A dataset is a folder containing a UTF-8 `metadata.csv` and its images. UTF-8 files with a byte-order mark are accepted.

The `image_name` column contains each image's relative filename. PNG, JPEG, TIFF, BMP, and WebP are supported by the native image tools; XOpat also provides deep-zoom rendering through Pillow/OpenSlide. Browser-native rendering support varies for TIFF and whole-slide formats, so use XOpat for those files.

```csv
image_name,synthetic,tissue,mpp_value
images/001.png,false,colon,0.5
images/002.png,true,colon,0.5
```

Keep filenames unique. Absolute paths and paths outside the dataset are rejected. Names without extensions can be resolved when a file with a supported extension exists, but explicit filenames are less ambiguous. Do not use symlinks to files outside the dataset.

Additional columns are optional metadata. Boolean values are `true` and `false`; finite numeric values become numbers; other values stay strings. Missing cells are treated as empty strings. Configure which attributes participants can see in the study schema. Filenames are accessible through image URLs and the API, so do not encode the answer or real/synthetic status in them if the study should be blinded.

Upload the whole folder from the Datasets page. Large files are sent in chunks. After upload, the application reports missing metadata, missing images, and unreferenced images. Correct validation errors before using the dataset. A dataset referenced by a study cannot be deleted until those references are removed.

For large server-side imports, place a dataset folder under `uploads/datasets/` with the same file ownership as the application's other uploads, then refresh the Datasets page.
