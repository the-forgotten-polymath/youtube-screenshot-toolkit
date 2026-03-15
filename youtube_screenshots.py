#!/usr/bin/env python3
"""
Enhanced YouTube Video Screenshot Capture Tool with HD Quality Guarantee
Usage: python youtube_screenshots.py <youtube_url> <interval_seconds>
Example: python youtube_screenshots.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 5

Features:
1. HD video download (1080p or 720p preferred) for maximum screenshot quality
2. High-quality screenshot extraction with HD preservation (PNG/JPEG options)
3. HD PDF generation with configurable DPI (images only)
4. Automatic transcript/subtitle download (saved as separate text file)
5. Complete duplicate removal
6. Video quality verification and format detection
7. PDF contains only high-quality screenshots
"""

import os
import sys
import re
import subprocess
import argparse
import tempfile
import shutil
from pathlib import Path
import json
import hashlib
from PIL import Image
import numpy as np
from datetime import timedelta
import textwrap

def sanitize_filename(filename, max_length=100):
    """Remove invalid characters from filename"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    filename = filename.strip('. ')
    filename = filename.replace(' ', '_')
    if len(filename) > max_length:
        filename = filename[:max_length]
    return filename

def format_time(seconds):
    """Convert seconds to readable format"""
    return str(timedelta(seconds=int(seconds)))

def debug_available_formats(url):
    """Debug function to show all available formats"""
    try:
        cmd = [
            'yt-dlp',
            '--list-formats',
            '--no-playlist',
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("\n🔍 DEBUG: All available formats:")
        print("=" * 60)
        print(result.stdout)
        print("=" * 60)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error listing formats: {e}")
        return False

def get_video_info(url, debug_formats=False):
    """Get video title, duration, available formats and subtitles using yt-dlp"""
    try:
        if debug_formats:
            debug_available_formats(url)
        
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-playlist',
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        
        # Check for available subtitles/captions
        subtitles_available = bool(info.get('subtitles', {})) or bool(info.get('automatic_captions', {}))
        
        # Get available formats and find HD options
        formats = info.get('formats', [])
        hd_formats = []
        all_formats = []
        
        for fmt in formats:
            height = fmt.get('height')
            width = fmt.get('width')
            format_id = fmt.get('format_id')
            ext = fmt.get('ext')
            vcodec = fmt.get('vcodec')
            acodec = fmt.get('acodec')
            filesize = fmt.get('filesize')
            
            format_info = {
                'format_id': format_id,
                'height': height,
                'width': width,
                'ext': ext,
                'fps': fmt.get('fps'),
                'vcodec': vcodec,
                'acodec': acodec,
                'filesize': filesize,
                'format_note': fmt.get('format_note', ''),
                'quality': fmt.get('quality')
            }
            
            all_formats.append(format_info)
            
            if height and height >= 720:
                hd_formats.append(format_info)
        
        # Sort HD formats by height (highest first)
        hd_formats.sort(key=lambda x: x['height'] if x['height'] else 0, reverse=True)
        
        return {
            'title': info.get('title', 'untitled'),
            'duration': info.get('duration', 0),
            'description': info.get('description', ''),
            'uploader': info.get('uploader', 'Unknown'),
            'upload_date': info.get('upload_date', ''),
            'view_count': info.get('view_count', 0),
            'subtitles_available': subtitles_available,
            'hd_formats': hd_formats,
            'all_formats': all_formats
        }
    except subprocess.CalledProcessError as e:
        print(f"Error getting video info: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing video info: {e}")
        return None

def download_video_and_transcript(url, video_path, transcript_path, force_hd=True):
    """Download YouTube video and transcript/subtitles using yt-dlp with aggressive HD quality forcing"""
    try:
        if force_hd:
            # AGGRESSIVE HD FORCING - Try multiple strategies
            format_options = [
                # Strategy 1: Force specific HD formats with quality requirements
                'bestvideo[height>=1080][ext=mp4]+bestaudio[ext=m4a]/best[height>=1080][ext=mp4]',
                'bestvideo[height>=720][ext=mp4]+bestaudio[ext=m4a]/best[height>=720][ext=mp4]',
                # Strategy 2: Force by format ID (common HD format IDs)
                '137+140/136+140/135+140/134+140',  # 1080p, 720p, 480p, 360p + audio
                # Strategy 3: Specific height requirements
                'best[height=1080]/best[height=720]/best[height>=720]',
                # Strategy 4: Quality-based selection
                'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                # Strategy 5: Last resort with minimum quality requirement
                'best[height>=480]/best'
            ]
            
            print("🎯 FORCING HD QUALITY DOWNLOAD...")
            print("   Trying multiple HD format strategies...")
            
        else:
            # Standard format selection
            format_options = ['best[ext=mp4]/best']
        
        cmd = [
            'yt-dlp',
            '-f', '/'.join(format_options),
            '--no-playlist',
            '--prefer-free-formats',  # Prefer free formats for better quality
            '--merge-output-format', 'mp4',  # Ensure MP4 output
            '-o', video_path,
            '--write-auto-subs',  # Download automatic captions if available
            '--write-subs',       # Download manual subtitles if available
            '--sub-lang', 'en',   # Prefer English subtitles
            '--convert-subs', 'srt',  # Convert to SRT format
            url
        ]
        
        print("Downloading video and attempting to fetch transcript...")
        subprocess.run(cmd, check=True)
        
        # Check if subtitle file was created
        video_dir = os.path.dirname(video_path)
        video_base = os.path.splitext(os.path.basename(video_path))[0]
        
        # Look for subtitle files
        subtitle_patterns = [
            f"{video_base}.en.srt",
            f"{video_base}.en.vtt",
            f"{video_base}.srt",
            f"{video_base}.vtt"
        ]
        
        subtitle_file = None
        for pattern in subtitle_patterns:
            potential_file = os.path.join(video_dir, pattern)
            if os.path.exists(potential_file):
                subtitle_file = potential_file
                break
        
        # If subtitle file exists, convert to plain text
        if subtitle_file:
            print(f"  ✓ Transcript found: {os.path.basename(subtitle_file)}")
            convert_srt_to_text(subtitle_file, transcript_path)
            return True, True  # Video downloaded, transcript found
        else:
            print("  ⚠ No transcript/captions available for this video")
            return True, False  # Video downloaded, no transcript
            
    except subprocess.CalledProcessError as e:
        print(f"Error downloading video: {e}")
        return False, False

def convert_srt_to_text(srt_file, text_file):
    """Convert SRT subtitle file to plain text transcript"""
    try:
        with open(srt_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        transcript_lines = []
        current_text = []
        
        for line in lines:
            line = line.strip()
            # Skip subtitle numbers and timestamps
            if line and not line.isdigit() and '-->' not in line:
                # Remove HTML tags if present
                line = re.sub('<[^<]+?>', '', line)
                current_text.append(line)
            elif not line and current_text:
                # Empty line indicates end of subtitle block
                transcript_lines.append(' '.join(current_text))
                current_text = []
        
        # Add any remaining text
        if current_text:
            transcript_lines.append(' '.join(current_text))
        
        # Write to text file
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write("VIDEO TRANSCRIPT\n")
            f.write("=" * 50 + "\n\n")
            
            # Join lines and format paragraphs
            full_text = ' '.join(transcript_lines)
            # Remove duplicate spaces
            full_text = re.sub(r'\s+', ' ', full_text)
            
            # Wrap text for better readability
            wrapped_text = textwrap.fill(full_text, width=80)
            f.write(wrapped_text)
        
        print(f"  ✓ Transcript saved to: {os.path.basename(text_file)}")
        return True
        
    except Exception as e:
        print(f"Error converting transcript: {e}")
        return False

def extract_high_quality_screenshots(video_path, output_dir, interval, title_prefix, quality='high'):
    """Extract maximum quality screenshots from video with aggressive HD settings"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Get video resolution
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        resolution_info = result.stdout.strip().split(',')
        
        # Get video duration
        cmd2 = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, check=True)
        duration = float(result2.stdout.strip())
        
        if len(resolution_info) >= 2:
            width, height = int(resolution_info[0]), int(resolution_info[1])
            print(f"Video resolution: {width}x{height}")
            print(f"Video duration: {duration:.1f} seconds")
            
            # Check if video is HD quality and warn if not
            if height >= 1080:
                print(f"✓ Full HD video detected ({height}p) - Excellent quality expected")
            elif height >= 720:
                print(f"✓ HD video detected ({height}p) - Good quality expected")
            else:
                print(f"⚠ Video quality is below HD ({height}p) - Consider finding a higher quality source")
        else:
            print(f"Video duration: {duration:.1f} seconds")
        
        print(f"Extracting maximum quality screenshots every {interval} seconds...")
        
        screenshots_taken = 0
        current_time = 0
        screenshot_files = []
        
        while current_time <= duration:
            time_str = f"{int(current_time):04d}s"
            
            # Always use PNG for maximum quality by default, unless specifically requesting JPEG
            if quality == 'high':
                # High quality JPEG with maximum settings
                output_file = os.path.join(output_dir, f"{title_prefix}_{time_str}.jpg")
                cmd = [
                    'ffmpeg',
                    '-ss', str(current_time),
                    '-i', video_path,
                    '-vframes', '1',
                    '-q:v', '1',  # Maximum JPEG quality
                    '-qmin', '1',  # Minimum quantizer
                    '-qmax', '1',  # Maximum quantizer (same as min for consistent quality)
                    '-vf', 'scale=iw:ih:flags=lanczos+accurate_rnd+full_chroma_int',  # Best scaling
                    '-pix_fmt', 'yuvj444p',  # Highest quality pixel format for JPEG
                    '-y',
                    output_file
                ]
            else:
                # Lossless PNG for absolute maximum quality
                output_file = os.path.join(output_dir, f"{title_prefix}_{time_str}.png")
                cmd = [
                    'ffmpeg',
                    '-ss', str(current_time),
                    '-i', video_path,
                    '-vframes', '1',
                    '-vf', 'scale=iw:ih:flags=lanczos+accurate_rnd+full_chroma_int',  # Best scaling
                    '-pix_fmt', 'rgb24',  # RGB for PNG
                    '-compression_level', '0',  # No compression for maximum quality
                    '-y',
                    output_file
                ]
            
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            
            screenshots_taken += 1
            screenshot_files.append(output_file)
            
            # Show progress
            progress = (current_time / duration) * 100
            print(f"  [{progress:5.1f}%] Screenshot at {format_time(current_time)} saved")
            
            current_time += interval
        
        return screenshots_taken, screenshot_files
        
    except subprocess.CalledProcessError as e:
        print(f"Error extracting screenshots: {e}")
        return 0, []
    except ValueError as e:
        print(f"Error parsing video duration: {e}")
        return 0, []

def get_image_hash(image_path):
    """Calculate hash of an image for comparison"""
    try:
        with open(image_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        print(f"Error hashing image {image_path}: {e}")
        return None

def are_images_identical(img1_path, img2_path):
    """Check if two images are identical"""
    try:
        hash1 = get_image_hash(img1_path)
        hash2 = get_image_hash(img2_path)
        
        if hash1 and hash2 and hash1 == hash2:
            return True
        
        img1 = Image.open(img1_path)
        img2 = Image.open(img2_path)
        
        if img1.mode != 'RGB':
            img1 = img1.convert('RGB')
        if img2.mode != 'RGB':
            img2 = img2.convert('RGB')
        
        if img1.size != img2.size:
            return False
        
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        
        return np.array_equal(arr1, arr2)
        
    except Exception as e:
        print(f"Error comparing images: {e}")
        return False

def remove_duplicate_screenshots(screenshot_files):
    """Remove duplicate screenshots"""
    if len(screenshot_files) <= 1:
        return 0
    
    print("\nRemoving duplicate screenshots...")
    
    duplicates_removed = 0
    files_to_remove = set()
    processed_hashes = {}
    
    for i, current_file in enumerate(screenshot_files):
        if current_file in files_to_remove:
            continue
        
        if not os.path.exists(current_file):
            continue
        
        current_hash = get_image_hash(current_file)
        if not current_hash:
            continue
        
        if current_hash in processed_hashes:
            files_to_remove.add(current_file)
        else:
            processed_hashes[current_hash] = current_file
            
            for j in range(i + 1, len(screenshot_files)):
                compare_file = screenshot_files[j]
                
                if compare_file in files_to_remove or not os.path.exists(compare_file):
                    continue
                
                if are_images_identical(current_file, compare_file):
                    files_to_remove.add(compare_file)
    
    if len(files_to_remove) > 0:
        print(f"  Removing {len(files_to_remove)} duplicate images...")
        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                duplicates_removed += 1
            except Exception as e:
                print(f"  Error removing {file_path}: {e}")
    
    return duplicates_removed

def verify_downloaded_video_quality(video_path):
    """Verify the quality of the downloaded video"""
    try:
        # Get video resolution
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        resolution_info = result.stdout.strip().split(',')
        
        # Get codec and bitrate separately
        cmd2 = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,bit_rate',
            '-of', 'csv=p=0',
            video_path
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, check=True)
        codec_info = result2.stdout.strip().split(',')
        
        if len(resolution_info) >= 2:
            width, height = int(resolution_info[0]), int(resolution_info[1])
            print(f"\n📹 Downloaded video quality verification:")
            print(f"   Resolution: {width}x{height}")
            
            # Add codec info if available
            if len(codec_info) >= 1 and codec_info[0]:
                print(f"   Codec: {codec_info[0]}")
            
            # Add bitrate info if available
            if len(codec_info) >= 2 and codec_info[1] and codec_info[1].isdigit():
                bitrate = int(codec_info[1])
                print(f"   Bitrate: {bitrate/1000:.0f} kbps")
            
            if height >= 1080:
                print(f"   ✅ Excellent quality: Full HD ({height}p)")
                return "excellent"
            elif height >= 720:
                print(f"   ✅ Good quality: HD ({height}p)")
                return "good"
            else:
                print(f"   ⚠️  Low quality: Below HD ({height}p)")
                return "low"
        
        return "unknown"
        
    except Exception as e:
        print(f"   Error verifying video quality: {e}")
        return "unknown"

def create_hd_pdf_images_only(images_dir, pdf_path, video_info, dpi=600):
    """Create maximum quality PDF from images only with enhanced settings"""
    try:
        print(f"\nCreating maximum quality PDF (DPI: {dpi})...")
        
        # Get all image files
        image_files = sorted(list(Path(images_dir).glob('*.jpg')) + list(Path(images_dir).glob('*.png')))
        
        if not image_files:
            print("  No images found to create PDF")
            return False
        
        print(f"  Found {len(image_files)} images to include in PDF")
        
        # Prepare images for PDF with maximum quality settings
        pdf_images = []
        
        # Add all screenshots with quality preservation
        print("  Processing screenshots for maximum PDF quality...")
        for i, img_path in enumerate(image_files):
            try:
                img = Image.open(img_path)
                
                # Convert to RGB if necessary, but preserve quality
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Don't resize - keep original resolution for maximum quality
                # Only resize if absolutely massive (over 4K)
                max_dimension = 4000  # Allow up to 4K resolution
                if img.width > max_dimension or img.height > max_dimension:
                    print(f"    Resizing very large image: {img.width}x{img.height}")
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                
                pdf_images.append(img)
                
                if (i + 1) % 5 == 0:
                    print(f"    Processed {i + 1}/{len(image_files)} images...")
                    
            except Exception as e:
                print(f"  Warning: Could not process {img_path}: {e}")
        
        # Save as maximum quality PDF
        print(f"  Saving maximum quality PDF...")
        
        if pdf_images:
            # Save with maximum quality settings
            pdf_images[0].save(
                pdf_path,
                "PDF",
                resolution=dpi,  # High DPI for better quality
                quality=100,  # Maximum quality setting
                optimize=False,  # Don't optimize to preserve quality
                save_all=True,
                append_images=pdf_images[1:] if len(pdf_images) > 1 else []
            )
            
            # Get file size
            file_size = os.path.getsize(pdf_path) / (1024 * 1024)
            
            print(f"  ✅ Maximum quality PDF created!")
            print(f"    - Screenshots: {len(image_files)}")
            print(f"    - DPI: {dpi}")
            print(f"    - Size: {file_size:.2f} MB")
            print(f"    - Quality: Maximum (no compression)")
            print(f"    - Location: {pdf_path}")
            
            return True
        
    except Exception as e:
        print(f"  Error creating PDF: {e}")
        return False



def verify_all_unique(images_dir):
    """Final verification that all remaining images are unique"""
    print("\nVerifying all images are unique...")
    
    # Get all image files in the directory
    image_files = sorted([str(f) for f in Path(images_dir).glob('*.jpg')] + 
                         [str(f) for f in Path(images_dir).glob('*.png')])
    
    if len(image_files) <= 1:
        print("  ✓ Only one or no images present - uniqueness guaranteed!")
        return True
    
    print(f"  Checking {len(image_files)} images...")
    
    # Store hashes of all images
    image_hashes = {}
    duplicates_found = []
    
    for img_path in image_files:
        img_hash = get_image_hash(img_path)
        if img_hash:
            if img_hash in image_hashes:
                # Found a duplicate
                duplicates_found.append((image_hashes[img_hash], img_path))
                print(f"  ✗ Found duplicate: {os.path.basename(image_hashes[img_hash])} == {os.path.basename(img_path)}")
            else:
                image_hashes[img_hash] = img_path
    
    if not duplicates_found:
        print(f"  ✓ All {len(image_files)} images are unique!")
        return True
    else:
        print(f"  ✗ Found {len(duplicates_found)} duplicate pairs")
        return False

def check_dependencies():
    """Check if required tools are installed"""
    dependencies = {
        'yt-dlp': 'yt-dlp --version',
        'ffmpeg': 'ffmpeg -version',
        'ffprobe': 'ffprobe -version'
    }
    
    missing = []
    for tool, cmd in dependencies.items():
        try:
            subprocess.run(cmd.split(), capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            missing.append(tool)
    
    try:
        import PIL
        import numpy
    except ImportError:
        print("\nError: Missing required Python packages.")
        print("Please install: pip install Pillow numpy")
        return False
    
    if missing:
        print("Error: Missing required dependencies:")
        for tool in missing:
            print(f"  - {tool}")
        print("\nInstallation instructions:")
        print("  Ubuntu/Debian: sudo apt-get install ffmpeg && pip install yt-dlp Pillow numpy")
        print("  macOS: brew install ffmpeg && pip install yt-dlp Pillow numpy")
        print("  Windows: Download ffmpeg from ffmpeg.org and install with: pip install yt-dlp Pillow numpy")
        return False
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Extract HD screenshots from YouTube videos with image-only PDF and separate transcript'
    )
    parser.add_argument('url', help='YouTube video URL')
    parser.add_argument('interval', type=int, help='Interval in seconds between screenshots')
    parser.add_argument('--keep-video', action='store_true', help='Keep the downloaded video file')
    parser.add_argument('--force-local-hd', action='store_true', help='Force download and keep HD video locally for maximum quality')
    parser.add_argument('--output-dir', default='.', help='Base directory for output')
    parser.add_argument('--no-duplicate-removal', action='store_true', help='Disable duplicate removal')
    parser.add_argument('--no-pdf', action='store_true', help='Skip PDF generation')
    parser.add_argument('--no-transcript', action='store_true', help='Skip transcript download')
    parser.add_argument('--quality', choices=['high', 'highest'], default='highest', 
                       help='Screenshot quality (high=max JPEG, highest=lossless PNG - recommended)')
    parser.add_argument('--pdf-dpi', type=int, default=600, 
                       help='PDF DPI resolution (default: 600, higher=better quality)')
    parser.add_argument('--debug-formats', action='store_true', help='Show all available formats for debugging')
    
    args = parser.parse_args()
    
    if args.interval <= 0:
        print("Error: Interval must be greater than 0")
        sys.exit(1)
    
    if not check_dependencies():
        sys.exit(1)
    
    # Get video information
    print(f"Fetching video information...")
    video_info = get_video_info(args.url, debug_formats=args.debug_formats)
    if not video_info:
        print("Error: Could not fetch video information")
        sys.exit(1)
    
    safe_title = sanitize_filename(video_info['title'])
    
    print(f"\n{'='*60}")
    print(f"Video: {video_info['title']}")
    print(f"Duration: {format_time(video_info['duration'])}")
    print(f"Uploader: {video_info['uploader']}")
    if video_info.get('view_count'):
        print(f"Views: {video_info['view_count']:,}")
    print(f"Subtitles available: {'Yes' if video_info['subtitles_available'] else 'No'}")
    
    # Display HD format information
    hd_formats = video_info.get('hd_formats', [])
    if hd_formats:
        print(f"HD formats available:")
        for fmt in hd_formats[:3]:  # Show top 3 HD formats
            print(f"  - {fmt['height']}p ({fmt['width']}x{fmt['height']}) {fmt.get('ext', 'unknown')} {fmt.get('fps', '?')}fps")
        if len(hd_formats) > 3:
            print(f"  ... and {len(hd_formats) - 3} more HD formats")
        print(f"✓ Will download best HD quality (1080p or 720p preferred)")
    else:
        print(f"⚠ No HD formats detected - screenshots may be lower quality")
    
    print(f"{'='*60}\n")
    
    # Create output directories
    base_dir = Path(args.output_dir)
    video_dir = base_dir / safe_title
    images_dir = video_dir / 'images'
    images_dir.mkdir(parents=True, exist_ok=True)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = os.path.join(temp_dir, 'video.mp4')
        transcript_path = video_dir / f"{safe_title}_transcript.txt"
        
        # Download video and transcript with HD forcing
        video_success, transcript_success = download_video_and_transcript(
            args.url, 
            video_path, 
            transcript_path if not args.no_transcript else None,
            force_hd=True
        )
        
        if not video_success:
            print("Error: Failed to download video")
            sys.exit(1)
        
        print(f"\n✓ Video downloaded successfully!")
        
        # Verify the quality of the downloaded video
        video_quality = verify_downloaded_video_quality(video_path)
        if video_quality == "low":
            print("⚠️  WARNING: Downloaded video is below HD quality. Screenshots may not be optimal.")
            print("   Consider finding a different video source with higher quality.")
        
        if not args.no_transcript and transcript_success:
            print(f"✓ Transcript saved as separate text file!")
        elif not args.no_transcript:
            print("⚠ Transcript not available for this video")
        
        # Extract high-quality screenshots
        print(f"\nExtracting {args.quality} quality screenshots...")
        screenshot_count, screenshot_files = extract_high_quality_screenshots(
            video_path, 
            images_dir, 
            args.interval,
            safe_title,
            args.quality
        )
        
        if screenshot_count > 0:
            print(f"\n✓ Extracted {screenshot_count} screenshots")
            
            # Remove duplicates
            if not args.no_duplicate_removal:
                duplicates_removed = remove_duplicate_screenshots(screenshot_files)
                if duplicates_removed > 0:
                    print(f"✓ Removed {duplicates_removed} duplicate screenshots")
                    print(f"  Final count: {screenshot_count - duplicates_removed} unique screenshots")
                
                # Verify all remaining images are unique
                verify_all_unique(images_dir)
            
            # Create HD PDF with images only
            if not args.no_pdf:
                pdf_path = video_dir / f"{safe_title}_HD.pdf"
                pdf_created = create_hd_pdf_images_only(
                    images_dir, 
                    pdf_path, 
                    video_info,
                    args.pdf_dpi
                )
                
                if not pdf_created:
                    print("\n⚠ Warning: PDF creation failed")
            
            # Keep video if requested or force local HD
            if args.keep_video or args.force_local_hd:
                final_video_path = video_dir / f"{safe_title}.mp4"
                shutil.copy2(video_path, final_video_path)
                if args.force_local_hd:
                    print(f"\n📹 HD Video stored locally: {final_video_path.absolute()}")
                    print(f"   Use this local file for maximum quality screenshots in future")
                else:
                    print(f"\n📹 Video saved to: {final_video_path.absolute()}")
            
            # Final summary
            print(f"\n{'='*60}")
            print(f"✅ COMPLETED SUCCESSFULLY!")
            print(f"{'='*60}")
            print(f"📁 Output directory: {video_dir.absolute()}")
            print(f"🖼️ Screenshots: {images_dir.absolute()}")
            if not args.no_pdf and pdf_created:
                print(f"📄 HD PDF (images only): {pdf_path.absolute()}")
            if transcript_success and not args.no_transcript:
                print(f"📝 Transcript (text file): {transcript_path.absolute()}")
            
            # List some of the final files
            remaining_files = sorted(list(Path(images_dir).glob('*.jpg')) + 
                                    list(Path(images_dir).glob('*.png')))
            if remaining_files:
                print(f"\nTotal unique screenshots: {len(remaining_files)}")
                if len(remaining_files) <= 5:
                    print("Files:")
                    for f in remaining_files:
                        print(f"  - {f.name}")
                else:
                    print("Sample files:")
                    for f in remaining_files[:3]:
                        print(f"  - {f.name}")
                    print(f"  ... and {len(remaining_files) - 3} more")
            
            print(f"{'='*60}\n")
            
        else:
            print("\nError: No screenshots were extracted")
            sys.exit(1)

if __name__ == "__main__":
    main()
