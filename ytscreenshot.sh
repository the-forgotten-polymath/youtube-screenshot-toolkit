#!/bin/bash

# YouTube Screenshot Batch Processor - Enhanced Bash Wrapper
# Supports both single URL and batch file processing
#
# Usage:
#   Single URL:  ./ytscreenshot.sh --url "https://youtube.com/..." --interval 10
#   Batch file:  ./ytscreenshot.sh --batch urls.txt --interval 10
#   With options: ./ytscreenshot.sh --batch urls.txt --interval 10 --workers 8 --quality highest

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    echo -e "${1}${2}${NC}"
}

# Function to print header
print_header() {
    echo ""
    print_color "$CYAN" "╔════════════════════════════════════════════════════════════╗"
    print_color "$CYAN" "║     YouTube Screenshot Batch Processor - Enhanced v2.0     ║"
    print_color "$CYAN" "╚════════════════════════════════════════════════════════════╝"
    echo ""
}

# Function to show usage
show_usage() {
    echo "Usage:"
    echo "  Single URL:"
    echo "    $0 --url \"https://youtube.com/watch?v=...\" --interval 10"
    echo ""
    echo "  Batch file:"
    echo "    $0 --batch urls.txt --interval 10"
    echo ""
    echo "Options:"
    echo "  --url URL           Process single YouTube URL"
    echo "  --batch FILE        Process URLs from text file (one per line)"
    echo "  --interval SECONDS  Screenshot interval in seconds (required)"
    echo "  --output-dir DIR    Output directory (default: current)"
    echo "  --quality high/highest  Quality setting (default: high)"
    echo "  --pdf-dpi DPI       PDF resolution (default: 300)"
    echo "  --workers N         Number of parallel workers (default: CPU cores)"
    echo "  --keep-video        Keep downloaded video files"
    echo "  --no-transcript     Skip transcript download"
    echo "  --no-pdf           Skip PDF generation"
    echo ""
    echo "Example batch file (urls.txt):"
    echo "  https://www.youtube.com/watch?v=video1"
    echo "  https://www.youtube.com/watch?v=video2"
    echo "  # Comments are ignored"
    echo "  https://www.youtube.com/watch?v=video3"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Function to check and install dependencies
check_dependencies() {
    local missing_deps=()
    
    print_color "$YELLOW" "Checking dependencies..."
    
    # Check Python 3
    if ! command_exists python3; then
        missing_deps+=("python3")
    else
        print_color "$GREEN" "  ✓ Python 3 installed"
    fi
    
    # Check ffmpeg
    if ! command_exists ffmpeg; then
        missing_deps+=("ffmpeg")
    else
        print_color "$GREEN" "  ✓ ffmpeg installed"
    fi
    
    # Check ffprobe
    if ! command_exists ffprobe; then
        missing_deps+=("ffprobe")
    else
        print_color "$GREEN" "  ✓ ffprobe installed"
    fi
    
    # Check yt-dlp
    if ! command_exists yt-dlp; then
        print_color "$YELLOW" "  ⚠ yt-dlp not found, attempting to install..."
        pip3 install --user yt-dlp &> /dev/null
        if [ $? -eq 0 ]; then
            print_color "$GREEN" "  ✓ yt-dlp installed successfully"
        else
            missing_deps+=("yt-dlp")
        fi
    else
        print_color "$GREEN" "  ✓ yt-dlp installed"
    fi
    
    # Check Python packages
    python3 -c "import PIL, numpy" 2>/dev/null
    if [ $? -ne 0 ]; then
        print_color "$YELLOW" "  ⚠ Python packages missing, installing..."
        pip3 install --user Pillow numpy &> /dev/null
        if [ $? -eq 0 ]; then
            print_color "$GREEN" "  ✓ Python packages installed"
        else
            missing_deps+=("Python packages (Pillow, numpy)")
        fi
    else
        print_color "$GREEN" "  ✓ Python packages installed"
    fi
    
    # Report missing dependencies
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_color "$RED" "\nError: Missing required dependencies:"
        for dep in "${missing_deps[@]}"; do
            print_color "$RED" "  ✗ $dep"
        done
        echo ""
        echo "Installation instructions:"
        echo "  Ubuntu/Debian:"
        echo "    sudo apt-get update"
        echo "    sudo apt-get install python3 python3-pip ffmpeg"
        echo "    pip3 install --user yt-dlp Pillow numpy"
        echo ""
        echo "  macOS:"
        echo "    brew install python3 ffmpeg"
        echo "    pip3 install --user yt-dlp Pillow numpy"
        echo ""
        echo "  Fedora:"
        echo "    sudo dnf install python3 python3-pip ffmpeg"
        echo "    pip3 install --user yt-dlp Pillow numpy"
        echo ""
        return 1
    fi
    
    print_color "$GREEN" "\n✓ All dependencies satisfied"
    return 0
}

# Function to get CPU count
get_cpu_count() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        nproc 2>/dev/null || echo 4
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        sysctl -n hw.ncpu 2>/dev/null || echo 4
    else
        echo 4
    fi
}

# Main script
main() {
    print_header
    
    # Parse arguments
    URL=""
    BATCH_FILE=""
    INTERVAL=""
    OUTPUT_DIR="."
    QUALITY="high"
    PDF_DPI="300"
    WORKERS="0"
    EXTRA_ARGS=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --url)
                URL="$2"
                shift 2
                ;;
            --batch)
                BATCH_FILE="$2"
                shift 2
                ;;
            --interval)
                INTERVAL="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --quality)
                QUALITY="$2"
                shift 2
                ;;
            --pdf-dpi)
                PDF_DPI="$2"
                shift 2
                ;;
            --workers)
                WORKERS="$2"
                shift 2
                ;;
            --keep-video)
                EXTRA_ARGS="$EXTRA_ARGS --keep-video"
                shift
                ;;
            --no-transcript)
                EXTRA_ARGS="$EXTRA_ARGS --no-transcript"
                shift
                ;;
            --no-pdf)
                EXTRA_ARGS="$EXTRA_ARGS --no-pdf"
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                print_color "$RED" "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Validate inputs
    if [[ -z "$URL" && -z "$BATCH_FILE" ]]; then
        print_color "$RED" "Error: Must specify either --url or --batch"
        show_usage
        exit 1
    fi
    
    if [[ -n "$URL" && -n "$BATCH_FILE" ]]; then
        print_color "$RED" "Error: Cannot specify both --url and --batch"
        show_usage
        exit 1
    fi
    
    if [[ -z "$INTERVAL" ]]; then
        print_color "$RED" "Error: --interval is required"
        show_usage
        exit 1
    fi
    
    # Validate interval is a number
    if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]]; then
        print_color "$RED" "Error: Interval must be a positive integer"
        exit 1
    fi
    
    # Validate batch file exists
    if [[ -n "$BATCH_FILE" && ! -f "$BATCH_FILE" ]]; then
        print_color "$RED" "Error: Batch file not found: $BATCH_FILE"
        exit 1
    fi
    
    # Check dependencies
    if ! check_dependencies; then
        exit 1
    fi
    
    # Get script directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PYTHON_SCRIPT="$SCRIPT_DIR/youtube_batch_processor.py"
    
    # Check if Python script exists
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        print_color "$RED" "Error: Python script not found: $PYTHON_SCRIPT"
        print_color "$YELLOW" "Make sure youtube_batch_processor.py is in the same directory as this script"
        exit 1
    fi
    
    # Show processing info
    echo ""
    print_color "$BLUE" "════════════════════════════════════════════════════════════"
    print_color "$MAGENTA" "Processing Configuration:"
    print_color "$BLUE" "════════════════════════════════════════════════════════════"
    
    if [[ -n "$URL" ]]; then
        print_color "$CYAN" "  Mode: Single URL"
        print_color "$CYAN" "  URL: $URL"
    else
        URL_COUNT=$(grep -v '^#' "$BATCH_FILE" | grep -v '^[[:space:]]*$' | wc -l)
        print_color "$CYAN" "  Mode: Batch Processing"
        print_color "$CYAN" "  Batch file: $BATCH_FILE"
        print_color "$CYAN" "  URLs to process: $URL_COUNT"
    fi
    
    print_color "$CYAN" "  Interval: $INTERVAL seconds"
    print_color "$CYAN" "  Output directory: $OUTPUT_DIR"
    print_color "$CYAN" "  Quality: $QUALITY"
    print_color "$CYAN" "  PDF DPI: $PDF_DPI"
    
    if [[ "$WORKERS" == "0" ]]; then
        CPU_COUNT=$(get_cpu_count)
        print_color "$CYAN" "  Workers: $CPU_COUNT (auto-detected)"
    else
        print_color "$CYAN" "  Workers: $WORKERS"
    fi
    
    print_color "$BLUE" "════════════════════════════════════════════════════════════"
    echo ""
    
    # Build Python command
    if [[ -n "$URL" ]]; then
        PYTHON_CMD="python3 \"$PYTHON_SCRIPT\" --url \"$URL\""
    else
        PYTHON_CMD="python3 \"$PYTHON_SCRIPT\" --batch \"$BATCH_FILE\""
    fi
    
    PYTHON_CMD="$PYTHON_CMD --interval $INTERVAL"
    PYTHON_CMD="$PYTHON_CMD --output-dir \"$OUTPUT_DIR\""
    PYTHON_CMD="$PYTHON_CMD --quality $QUALITY"
    PYTHON_CMD="$PYTHON_CMD --pdf-dpi $PDF_DPI"
    
    if [[ "$WORKERS" != "0" ]]; then
        PYTHON_CMD="$PYTHON_CMD --workers $WORKERS"
    fi
    
    PYTHON_CMD="$PYTHON_CMD $EXTRA_ARGS"
    
    # Run the Python script
    print_color "$GREEN" "Starting processing..."
    echo ""
    
    # Execute with proper error handling
    eval $PYTHON_CMD
    RESULT=$?
    
    # Check result
    echo ""
    if [ $RESULT -eq 0 ]; then
        print_color "$GREEN" "╔════════════════════════════════════════════════════════════╗"
        print_color "$GREEN" "║           ✓ Processing completed successfully!             ║"
        print_color "$GREEN" "╚════════════════════════════════════════════════════════════╝"
    else
        print_color "$RED" "╔════════════════════════════════════════════════════════════╗"
        print_color "$RED" "║             ✗ Processing failed with errors                ║"
        print_color "$RED" "╚════════════════════════════════════════════════════════════╝"
        exit 1
    fi
}

# Create sample URLs file if requested
if [[ "$1" == "--create-sample" ]]; then
    cat > sample_urls.txt << 'EOF'
# YouTube URLs for batch processing
# One URL per line, lines starting with # are ignored

# Educational videos
https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Add more URLs below
# https://www.youtube.com/watch?v=example1
# https://www.youtube.com/watch?v=example2
EOF
    print_color "$GREEN" "Created sample_urls.txt"
    print_color "$CYAN" "Edit this file and add your YouTube URLs, then run:"
    print_color "$YELLOW" "  $0 --batch sample_urls.txt --interval 10"
    exit 0
fi

# Run main function
main "$@"
