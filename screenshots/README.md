# Screenshot sources

These screenshots show SPaRE 1.0 running in Chromium with an isolated demonstration database. They are browser captures of the application, with no composited controls or generated tissue imagery.

| Screenshot | Resolution | Contents |
| --- | --- | --- |
| [Participant evaluation](participant-evaluate.jpg) | 3840 × 2400 | Real GTEx tissue, six selected ratings, and saved progress |
| [Dataset selection](admin-project-dataset.png) | 3200 × 2000 | Real tissue thumbnails and study image selection |
| [User management](admin-users.png) | 3200 × 2000 | Administrator, participant, and test accounts |
| [Participant progress](admin-project-participants.png) | 3200 × 2000 | Completion percentages and submission status |
| [Rating form configuration](admin-project-schema.png) | 3200 × 2400 | Pathology criteria, question descriptions, and configurable score labels |

Captures use a device pixel ratio of 2. The image-heavy participant capture is a quality-95 JPEG; the administration views are PNGs. Accounts, institutions, ratings, and results are fictional examples for demonstrating the software; they are not research findings or clinical assessments. Demonstration data is not installed by the production setup.

## Tissue images

All tissue images were extracted from real whole-slide files in `/data/GTEX`, from the [GTEx Histology Viewer collection](https://gtexportal.org/home/histologyPage). The featured slide, **GTEX-1117F-0326**, is listed there as *Nerve – Tibial*.

Each region is **4096 × 4096 pixels**, read at level 0 with OpenSlide and saved as an RGB JPEG at quality 95. No tissue was generated, retouched, or upscaled. Coordinates below are the top-left corner in level-0 pixels; the source resolution is approximately 0.4942 µm/pixel.

| Region | Source slide | x | y |
| --- | --- | ---: | ---: |
| 01 | GTEX-1117F-0126.svs | 8947 | 25009 |
| 02 | GTEX-1117F-0126.svs | 10547 | 25009 |
| **03 (featured)** | **GTEX-1117F-0326.svs** | **6238** | **13232** |
| 04 | GTEX-1117F-0326.svs | 7838 | 13232 |
| 05 | GTEX-1117F-0426.svs | 11098 | 11579 |
| 06 | GTEX-1117F-0426.svs | 12698 | 11579 |
| 07 | GTEX-1117F-1026.svs | 7154 | 5359 |
| 08 | GTEX-1117F-1026.svs | 8754 | 5359 |
| 09 | GTEX-1117F-1126.svs | 11337 | 23184 |
| 10 | GTEX-1117F-1126.svs | 12937 | 23184 |
| 11 | GTEX-1117F-1226.svs | 32373 | 6760 |
| 12 | GTEX-1117F-1226.svs | 33973 | 6760 |

The evaluation view displays region 03 as image 6. Its selected example scores are F1=2, F2=2, F3=1, F4=2, F5=2, and F6=1. The dataset-selection view shows a draft study containing eight of the twelve regions. The rating-form view shows the draft study's question editor with the nuclear-detail criterion expanded to display its description, score range, and labels.

Only the screenshots are included in this repository; the source whole-slide files and extracted dataset remain outside it. Consult the [GTEx FAQ](https://www.gtexportal.org/home/faq) for image access information.
