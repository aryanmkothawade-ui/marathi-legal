# High-Volume OCR Extraction Plan (`01_extract.py`)

Since we are dealing with **thousands** of legal PDFs, running OCR sequentially on a single CPU core would likely take days or weeks. Furthermore, if the script crashes halfway through, starting over would be a disaster. 

This plan completely overhauls the extraction pipeline to be industrial-grade, combining the high-quality image processing from your notebook with massive speed improvements.

## User Review Required

> [!WARNING]
> **CPU Usage**: This plan will use `multiprocessing` to max out your CPU cores and process multiple PDFs at the same time. While this script is running, your computer might be sluggish for other tasks. 

> [!IMPORTANT]
> **Tesseract Models**: We will be using the `--oem 1` configuration from your notebook. You must ensure that the `mar.traineddata` (Marathi LSTM model) is installed in your Tesseract environment, otherwise, the OCR will fail.

## Proposed Changes

### pipeline

#### [MODIFY] [01_extract.py](file:///c:/Users/bigha/OneDrive/Desktop/marathi_legal_document/pipeline/01_extract.py)
- **Directory Fix**: Change `PDF_DIR = BASE_DIR` to `PDF_DIR = os.path.join(BASE_DIR, "pdfs")` so it reads from the correct folder.
- **Checkpointing / Skip Logic**: Modify the script to check if `{doc_id}.txt` already exists in `corpus/raw_text/`. If it does, **skip the PDF entirely**. This ensures that if the script crashes or you stop it, you can simply run it again and it will pick up exactly where it left off without wasting hours re-OCRing PDFs it already finished.
- **Multiprocessing**: Wrap the main extraction loop in a `concurrent.futures.ProcessPoolExecutor`. This will process $N$ PDFs at the same time (where $N$ is the number of CPU cores you have), easily making the script 4x to 8x faster.
- **Advanced Image Preprocessing**: Integrate the `preprocess_image()` function from your notebook. Before passing the PDF page to Tesseract, we will use Pillow (`PIL.ImageOps`, `PIL.ImageFilter`) to apply:
  - Grayscale
  - Autocontrast
  - Sharpening
  - Simple Binarization Thresholding (128)
- **Tesseract Config**: Update the `pytesseract.image_to_string` call to include `config="--oem 1 --psm 3"` to use the LSTM engine and preserve paragraph blocks/lists correctly for legal texts.

## Verification Plan

### Automated Tests
- I will run the updated script on just 5 random PDFs from the `pdfs/` folder to verify that multiprocessing works, the text quality is high, and the script exits cleanly.

### Manual Verification
- You can check the `corpus/raw_text/` folder and read a few generated `.txt` files to ensure the OCR quality matches what you saw in your notebook.
