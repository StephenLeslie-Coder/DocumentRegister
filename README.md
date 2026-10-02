# Document Register

Document Register reads the first page of scanned PDF correspondence, extracts **Origin**, **To**, **From**, **Subject**, and a stamped **Receipt Date**, and writes approved records to an Excel register. Processing stays on the computer. The application does not upload documents or send telemetry.

## END USER

1. Download `DocumentRegisterSetup.exe` from the repository's **Releases** page, install it, and open Document Register from the Start Menu.
2. Select the folder containing your PDF documents. PDFs in subfolders are not included.
3. On first launch, select an existing Excel register or create a new one. The register may be in any folder you choose.
4. Click **Process Documents**.
5. Review documents marked **Needs Review**. Compare page one with all five extracted fields, correct them if needed, and click **Approve & Save**. Enter Receipt Date as `DD-Mon-YYYY`, for example `01-Oct-2026`. Use **Previous** and **Next** to move through the review queue.

Documents marked **Processed** are saved automatically. **Needs Review** and **Failed** documents are not saved automatically. **Already Processed** documents do not create another row. You can still use **Open PDF** from the review window.

## DEVELOPMENT

### Setup and run from source

Use Windows and Python 3.11 or newer. Install [Tesseract OCR with English data](https://tesseract-ocr.github.io/tessdoc/Installation.html) on the development/build computer. The application finds it in the usual `Program Files\Tesseract-OCR` location. If installed elsewhere, set `TESSERACT_CMD` to the full executable path for source runs.

```powershell
cd "C:\path\to\DocumentScanner"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe desktop.py
```

The command-line proof of concept is still available. Add `--diagnostics` only while developing; it prints raw OCR evidence and may show sensitive correspondence text.

```powershell
.\.venv\Scripts\python.exe main.py "C:\path\to\pdf-or-folder"
```

### Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover label extraction, origin and stamp-date detection, OCR variations, PDF sample integration, folder discovery, register creation and migration, duplicate detection, settings, approval validation, and preview scaling. The two real sample PDFs are private development fixtures: they are excluded from the repository and production distribution. To run the PDF integration test on another development computer, place those files in the local `samples` folder first.

### Build the portable application

The build computer needs Tesseract with `eng.traineddata` and the Python dependencies above.

```powershell
.\build.ps1
```

For a nonstandard Tesseract location, use `.\build.ps1 -TesseractHome "C:\path\to\Tesseract-OCR"`. The PyInstaller specification creates `dist\Document Register\Document Register.exe`. Distribute the **entire folder** for portable use. It includes the Python runtime, Tesseract executable and DLLs, and English OCR data. The packaged application selects its bundled Tesseract path automatically; recipients do not need Tesseract installed or on `PATH`.

### Build the installer

Install [Inno Setup 6](https://jrsoftware.org/isdl.php) on the build computer, then build the portable application first:

```powershell
.\build.ps1
.\build-installer.ps1
```

If `ISCC.exe` is not in a standard location, pass `-CompilerPath "C:\path\to\ISCC.exe"`. The output is `dist\installer\DocumentRegisterSetup.exe`. The installer includes the complete portable distribution, installs per user under `%LOCALAPPDATA%\Programs\Document Register`, adds a Start Menu shortcut and uninstaller, and offers an optional Desktop shortcut. It does not include `samples` or a default Excel workbook. Normal upgrades keep settings because they are stored separately from the install directory.

The application and installer versions come from `src/config.py` (`APP_VERSION`). The About dialog shows that version.

### Architecture and application data

`PDF → PyMuPDF first-page render → Pillow preprocessing → OCRService/Tesseract → OCR lines → correspondence and origin extraction → DocumentResult → review/Excel`. A separate high-contrast OCR pass is used for receipt-stamp detection when needed; it does not replace the normal OCR used for names or subject.

`desktop.py` contains the Tkinter interface and background worker. `src/app_logic.py` handles document discovery, processing decisions, approval, and settings. The OCR and extraction modules remain independent of the GUI. The parser uses semantic labels and OCR line context rather than fixed page coordinates. The review preview renders page one in memory and does not run OCR again. Receipt Date is only accepted from a received stamp or a date-only stamp with organizational context; the printed document Date is kept as a diagnostic and never substituted automatically.

Settings contain paths only and are stored in `%APPDATA%\DocumentRegister\settings.json`. Operational logs are stored in `%LOCALAPPDATA%\DocumentRegister\document-register.log`. Neither stores OCR text or extracted fields. Preview images are kept in memory. The Excel register stays wherever the user chooses. Its eight visible columns are File Name, Origin, To, From, Subject, Receipt Date, Processed Date, and Status. Receipt Date is written as an Excel date. Existing seven-column registers are migrated in place while preserving rows and duplicate keys. Duplicate detection uses filename plus SHA-256, stored in a hidden workbook column.

### Known limitations

- Poor scans, unusual templates, names spanning multiple lines, and unclear or missing receipt stamps can require manual review. An approval stamp is not treated as a received stamp. The review threshold intentionally favors review when extraction is uncertain.
- Unsaved review edits remain in memory only. Closing the application before approval requires reprocessing those PDFs.
- Avoid concurrent writes to the same workbook. If Excel locks the workbook, close it and retry saving.
- The installer is not code signed. Test the installer on a clean Windows computer before distributing it to other users.
