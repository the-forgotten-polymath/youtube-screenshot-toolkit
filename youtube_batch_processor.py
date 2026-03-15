#!/usr/bin/env python3
"""
Batch YouTube Screenshot Processor with Parallel Processing
Processes multiple YouTube videos concurrently using all available CPU cores

Usage:
  Single video: python youtube_batch_processor.py --url "https://youtube.com/..." --interval 10
  Batch file:   python youtube_batch_processor.py --batch urls.txt --interval 10
  
The batch file should contain one URL per line.
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
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import time
from typing import List, Tuple, Dict, Optional
import logging
from functools import partial
import asyncio
import aiofiles
import threading
import queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class VideoProcessor:
    """Handles processing of individual videos"""
    
    def __init__(self, interval: int, output_dir: str, quality: str = 'high', 
                 pdf_dpi: int = 300, keep_video: bool = False, 
                 no_transcript: bool = False, no_pdf: bool = False):
        self.interval = interval
        self.output_dir = output_dir
        self.quality = quality
        self.pdf_dpi = pdf_dpi
        self.keep_video = keep_video
        self.no_transcript = no_transcript
        self.no_pdf = no_pdf
    
    @staticmethod
    def sanitize_filename(filename: str, max_length: int = 100) -> str:
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        filename = filename.strip('. ')
        filename = filename.replace(' ', '_')
        if len(filename) > max_length:
            filename = filename[:max_length]
        return filename
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """Convert seconds to readable format"""
        return str(timedelta(seconds=int(seconds)))
    
    def get_video_info(self, url: str) -> Optional[Dict]:
        """Get video information using yt-dlp"""
        try:
            cmd = ['yt-dlp', '--dump-json', '--no-playlist', url]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            info = json.loads(result.stdout)
            
            subtitles_available = bool(info.get('subtitles', {})) or bool(info.get('automatic_captions', {}))
            
            return {
                'url': url,
                'title': info.get('title', 'untitled'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'subtitles_available': subtitles_available
            }
        except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error getting video info for {url}: {e}")
            return None
    
    def download_video(self, url: str, video_path: str, transcript_path: Optional[str] = None) -> Tuple[bool, bool]:
        """Download video and optionally transcript"""
        try:
            cmd = [
                'yt-dlp',
                '-f', 'best[ext=mp4]/best',
                '--no-playlist',
                '-o', video_path,
            ]
            
            if transcript_path and not self.no_transcript:
                cmd.extend([
                    '--write-auto-subs',
                    '--write-subs',
                    '--sub-lang', 'en',
                    '--convert-subs', 'srt'
                ])
            
            subprocess.run(cmd, check=True, timeout=300, 
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Check for transcript
            transcript_found = False
            if transcript_path and not self.no_transcript:
                video_dir = os.path.dirname(video_path)
                video_base = os.path.splitext(os.path.basename(video_path))[0]
                
                subtitle_patterns = [
                    f"{video_base}.en.srt",
                    f"{video_base}.en.vtt",
                    f"{video_base}.srt",
                    f"{video_base}.vtt"
                ]
                
                for pattern in subtitle_patterns:
                    potential_file = os.path.join(video_dir, pattern)
                    if os.path.exists(potential_file):
                        self.convert_srt_to_text(potential_file, transcript_path)
                        transcript_found = True
                        break
            
            return True, transcript_found
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error downloading video: {e}")
            return False, False
    
    def convert_srt_to_text(self, srt_file: str, text_file: str) -> bool:
        """Convert SRT subtitle file to plain text"""
        try:
            with open(srt_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            transcript_lines = []
            current_text = []
            
            for line in lines:
                line = line.strip()
                if line and not line.isdigit() and '-->' not in line:
                    line = re.sub('<[^<]+?>', '', line)
                    current_text.append(line)
                elif not line and current_text:
                    transcript_lines.append(' '.join(current_text))
                    current_text = []
            
            if current_text:
                transcript_lines.append(' '.join(current_text))
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write("VIDEO TRANSCRIPT\n")
                f.write("=" * 50 + "\n\n")
                full_text = ' '.join(transcript_lines)
                full_text = re.sub(r'\s+', ' ', full_text)
                wrapped_text = textwrap.fill(full_text, width=80)
                f.write(wrapped_text)
            
            return True
        except Exception as e:
            logger.error(f"Error converting transcript: {e}")
            return False
    
    def extract_screenshots(self, video_path: str, output_dir: str, title_prefix: str) -> List[str]:
        """Extract screenshots from video"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Get video duration
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            
            screenshot_files = []
            current_time = 0
            
            while current_time <= duration:
                time_str = f"{int(current_time):04d}s"
                
                if self.quality == 'highest':
                    output_file = os.path.join(output_dir, f"{title_prefix}_{time_str}.png")
                    cmd = [
                        'ffmpeg', '-ss', str(current_time),
                        '-i', video_path, '-vframes', '1',
                        '-vf', 'scale=iw:ih', '-y', output_file
                    ]
                else:
                    output_file = os.path.join(output_dir, f"{title_prefix}_{time_str}.jpg")
                    cmd = [
                        'ffmpeg', '-ss', str(current_time),
                        '-i', video_path, '-vframes', '1',
                        '-q:v', '1', '-vf', 'scale=iw:ih',
                        '-y', output_file
                    ]
                
                subprocess.run(cmd, stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL, check=True)
                screenshot_files.append(output_file)
                current_time += self.interval
            
            return screenshot_files
            
        except Exception as e:
            logger.error(f"Error extracting screenshots: {e}")
            return []
    
    def remove_duplicates(self, screenshot_files: List[str]) -> int:
        """Remove duplicate screenshots"""
        if len(screenshot_files) <= 1:
            return 0
        
        duplicates_removed = 0
        files_to_remove = set()
        processed_hashes = {}
        
        for current_file in screenshot_files:
            if current_file in files_to_remove or not os.path.exists(current_file):
                continue
            
            with open(current_file, 'rb') as f:
                current_hash = hashlib.sha256(f.read()).hexdigest()
            
            if current_hash in processed_hashes:
                files_to_remove.add(current_file)
            else:
                processed_hashes[current_hash] = current_file
        
        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                duplicates_removed += 1
            except Exception:
                pass
        
        return duplicates_removed
    
    def create_pdf(self, images_dir: str, pdf_path: str) -> bool:
        """Create PDF from images"""
        if self.no_pdf:
            return False
        
        try:
            image_files = sorted(list(Path(images_dir).glob('*.jpg')) + 
                               list(Path(images_dir).glob('*.png')))
            
            if not image_files:
                return False
            
            pdf_images = []
            for img_path in image_files:
                try:
                    img = Image.open(img_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    max_dimension = 3000
                    if img.width > max_dimension or img.height > max_dimension:
                        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                    
                    pdf_images.append(img)
                except Exception:
                    pass
            
            if pdf_images:
                pdf_images[0].save(
                    pdf_path, "PDF",
                    resolution=self.pdf_dpi,
                    quality=95,
                    optimize=True,
                    save_all=True,
                    append_images=pdf_images[1:] if len(pdf_images) > 1 else []
                )
                return True
            
        except Exception as e:
            logger.error(f"Error creating PDF: {e}")
        
        return False
    
    def process_video(self, url: str, job_id: int) -> Dict:
        """Process a single video"""
        start_time = time.time()
        result = {
            'url': url,
            'job_id': job_id,
            'success': False,
            'error': None,
            'duration': 0,
            'screenshots': 0,
            'pdf_created': False,
            'transcript_saved': False
        }
        
        try:
            # Get video info
            logger.info(f"[Job {job_id}] Fetching info for: {url}")
            video_info = self.get_video_info(url)
            if not video_info:
                result['error'] = "Failed to get video info"
                return result
            
            # Setup directories
            safe_title = self.sanitize_filename(video_info['title'])
            video_dir = Path(self.output_dir) / safe_title
            images_dir = video_dir / 'images'
            images_dir.mkdir(parents=True, exist_ok=True)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                video_path = os.path.join(temp_dir, 'video.mp4')
                transcript_path = video_dir / f"{safe_title}_transcript.txt"
                
                # Download video
                logger.info(f"[Job {job_id}] Downloading: {video_info['title']}")
                video_success, transcript_success = self.download_video(
                    url, video_path, transcript_path if not self.no_transcript else None
                )
                
                if not video_success:
                    result['error'] = "Failed to download video"
                    return result
                
                result['transcript_saved'] = transcript_success
                
                # Extract screenshots
                logger.info(f"[Job {job_id}] Extracting screenshots...")
                screenshot_files = self.extract_screenshots(video_path, images_dir, safe_title)
                
                if screenshot_files:
                    # Remove duplicates
                    duplicates = self.remove_duplicates(screenshot_files)
                    result['screenshots'] = len(screenshot_files) - duplicates
                    
                    # Create PDF
                    if not self.no_pdf:
                        pdf_path = video_dir / f"{safe_title}_HD.pdf"
                        result['pdf_created'] = self.create_pdf(images_dir, pdf_path)
                    
                    # Keep video if requested
                    if self.keep_video:
                        final_video_path = video_dir / f"{safe_title}.mp4"
                        shutil.copy2(video_path, final_video_path)
                    
                    result['success'] = True
                    logger.info(f"[Job {job_id}] ✓ Completed: {video_info['title']}")
                else:
                    result['error'] = "No screenshots extracted"
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"[Job {job_id}] Error processing {url}: {e}")
        
        result['duration'] = time.time() - start_time
        return result


def process_video_wrapper(args: Tuple) -> Dict:
    """Wrapper function for multiprocessing"""
    url, job_id, processor_params = args
    processor = VideoProcessor(**processor_params)
    return processor.process_video(url, job_id)


class BatchProcessor:
    """Handles batch processing of multiple videos"""
    
    def __init__(self, urls: List[str], **processor_params):
        self.urls = urls
        self.processor_params = processor_params
        self.num_workers = min(mp.cpu_count(), len(urls))
        
    def process_parallel(self) -> List[Dict]:
        """Process videos in parallel using all CPU cores"""
        logger.info(f"Starting batch processing of {len(self.urls)} videos")
        logger.info(f"Using {self.num_workers} parallel workers")
        
        # Prepare arguments for each job
        job_args = [
            (url, idx + 1, self.processor_params) 
            for idx, url in enumerate(self.urls)
        ]
        
        results = []
        start_time = time.time()
        
        # Use ProcessPoolExecutor for CPU-bound tasks
        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
            # Submit all jobs
            futures = {
                executor.submit(process_video_wrapper, args): args[1] 
                for args in job_args
            }
            
            # Process completed jobs
            completed = 0
            for future in as_completed(futures):
                job_id = futures[future]
                try:
                    result = future.result(timeout=600)  # 10 min timeout per video
                    results.append(result)
                    completed += 1
                    
                    # Progress update
                    progress = (completed / len(self.urls)) * 100
                    logger.info(f"Progress: {completed}/{len(self.urls)} ({progress:.1f}%)")
                    
                except Exception as e:
                    logger.error(f"Job {job_id} failed: {e}")
                    results.append({
                        'job_id': job_id,
                        'success': False,
                        'error': str(e)
                    })
        
        total_time = time.time() - start_time
        
        # Print summary
        self.print_summary(results, total_time)
        
        return results
    
    def print_summary(self, results: List[Dict], total_time: float):
        """Print processing summary"""
        successful = sum(1 for r in results if r.get('success', False))
        failed = len(results) - successful
        total_screenshots = sum(r.get('screenshots', 0) for r in results)
        
        print("\n" + "=" * 60)
        print("BATCH PROCESSING SUMMARY")
        print("=" * 60)
        print(f"Total videos: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Total screenshots: {total_screenshots}")
        print(f"Total time: {self.format_time(total_time)}")
        print(f"Average time per video: {self.format_time(total_time / len(results))}")
        
        if failed > 0:
            print("\nFailed videos:")
            for r in results:
                if not r.get('success', False):
                    print(f"  - Job {r.get('job_id')}: {r.get('url')} - {r.get('error')}")
        
        print("=" * 60)
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds to readable time"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"


def read_urls_from_file(filepath: str) -> List[str]:
    """Read URLs from a text file"""
    urls = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # Skip empty lines and comments
                    urls.append(line)
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
    return urls


def check_dependencies() -> bool:
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
        print("Error: Missing required Python packages.")
        print("Please install: pip install Pillow numpy")
        return False
    
    if missing:
        print("Error: Missing required dependencies:")
        for tool in missing:
            print(f"  - {tool}")
        print("\nInstallation instructions:")
        print("  Ubuntu/Debian: sudo apt-get install ffmpeg && pip install yt-dlp Pillow numpy")
        print("  macOS: brew install ffmpeg && pip install yt-dlp Pillow numpy")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Batch YouTube Screenshot Processor with Parallel Processing'
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--url', help='Single YouTube video URL')
    input_group.add_argument('--batch', help='Path to text file containing URLs (one per line)')
    
    # Processing options
    parser.add_argument('--interval', type=int, required=True, 
                       help='Interval in seconds between screenshots')
    parser.add_argument('--output-dir', default='.', 
                       help='Base directory for output (default: current directory)')
    parser.add_argument('--quality', choices=['high', 'highest'], default='high',
                       help='Screenshot quality (high=JPEG, highest=PNG)')
    parser.add_argument('--pdf-dpi', type=int, default=300,
                       help='PDF DPI resolution (default: 300)')
    parser.add_argument('--keep-video', action='store_true',
                       help='Keep the downloaded video files')
    parser.add_argument('--no-transcript', action='store_true',
                       help='Skip transcript download')
    parser.add_argument('--no-pdf', action='store_true',
                       help='Skip PDF generation')
    parser.add_argument('--workers', type=int, default=0,
                       help='Number of parallel workers (default: number of CPU cores)')
    
    args = parser.parse_args()
    
    # Validate dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Validate interval
    if args.interval <= 0:
        print("Error: Interval must be greater than 0")
        sys.exit(1)
    
    # Get URLs
    urls = []
    if args.url:
        urls = [args.url]
    elif args.batch:
        urls = read_urls_from_file(args.batch)
        if not urls:
            print(f"Error: No valid URLs found in {args.batch}")
            sys.exit(1)
    
    # Set number of workers
    if args.workers > 0:
        num_workers = args.workers
    else:
        num_workers = mp.cpu_count()
    
    # Prepare processor parameters
    processor_params = {
        'interval': args.interval,
        'output_dir': args.output_dir,
        'quality': args.quality,
        'pdf_dpi': args.pdf_dpi,
        'keep_video': args.keep_video,
        'no_transcript': args.no_transcript,
        'no_pdf': args.no_pdf
    }
    
    # Process videos
    print(f"\n{'='*60}")
    print(f"YouTube Batch Screenshot Processor")
    print(f"{'='*60}")
    print(f"Videos to process: {len(urls)}")
    print(f"Interval: {args.interval} seconds")
    print(f"Quality: {args.quality}")
    print(f"PDF DPI: {args.pdf_dpi}")
    print(f"Workers: {num_workers}")
    print(f"{'='*60}\n")
    
    if len(urls) == 1:
        # Single video - process directly
        processor = VideoProcessor(**processor_params)
        result = processor.process_video(urls[0], 1)
        
        if result['success']:
            print(f"\n✓ Successfully processed: {urls[0]}")
            print(f"  Screenshots: {result['screenshots']}")
            print(f"  PDF created: {result['pdf_created']}")
            print(f"  Transcript saved: {result['transcript_saved']}")
        else:
            print(f"\n✗ Failed to process: {urls[0]}")
            print(f"  Error: {result['error']}")
    else:
        # Multiple videos - use batch processor
        batch_processor = BatchProcessor(urls, **processor_params)
        batch_processor.num_workers = num_workers
        results = batch_processor.process_parallel()
    
    print("\n✅ Processing complete!")


if __name__ == "__main__":
    main()
