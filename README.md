# DXF Layer Extractor

A simple web application to extract and display layer information from DXF (Drawing Exchange Format) files.

## Features

- Upload DXF files (up to 100 MB)
- Extract all layer names from the drawing
- Display sorted layer list with count
- Support for DXF versions R12 through R2018+
- Clean, modern web interface
- Secure file handling

## Technology Stack

- **Backend**: Python 3 + Flask
- **DXF Parser**: ezdxf (actively maintained, modern library)
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd layerslist
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running Locally

1. Activate the virtual environment (if not already activated):
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Run the application:
```bash
python app.py
```

3. Open your browser and navigate to:
```
http://localhost:8080
```

## Usage

1. Click "Choose DXF File" to select a DXF file from your computer
2. Click "Extract Layers" to upload and process the file
3. View the extracted layer information:
   - File name and DXF version
   - Total layer count
   - Complete sorted list of all layers

## Deployment

### Render (Recommended)

1. Create a `render.yaml` file (coming soon)
2. Connect your GitHub repository to Render
3. Deploy as a Web Service

### Docker

1. Build the image:
```bash
docker build -t dxf-layers .
```
2. Run the container:
```bash
docker run -p 8080:8080 dxf-layers
```

## Future Enhancements

- Layer metadata (color, linetype, on/off, frozen/locked)
- Entity count per layer
- Export results to CSV
- Preview thumbnail (SVG render)
- Batch upload support
- API endpoint for programmatic access

## License

MIT License

## Contributing

Pull requests are welcome! For major changes, please open an issue first.
