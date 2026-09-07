"""
Screenshot Capture Module

This module provides functionality to capture screenshots of game applications.
"""

from PIL import Image
import pyautogui
from typing import Optional, Tuple
from pathlib import Path


class ScreenshotCapture:
    """
    Captures screenshots of game applications for AI analysis.
    
    This class provides methods to capture the entire screen or specific regions,
    which can then be fed into the AI decision engine for game state analysis.
    """
    
    def __init__(self, save_screenshots: bool = False, output_dir: str = "screenshots"):
        """
        Initialize the screenshot capture system.
        
        Args:
            save_screenshots: Whether to save screenshots to disk for debugging
            output_dir: Directory to save screenshots if save_screenshots is True
        """
        self.save_screenshots = save_screenshots
        self.output_dir = Path(output_dir)
        self.screenshot_count = 0
        
        if self.save_screenshots:
            self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def capture_full_screen(self) -> Image.Image:
        """
        Capture the entire screen.
        
        Returns:
            PIL Image object containing the screenshot
        """
        screenshot = pyautogui.screenshot()
        
        if self.save_screenshots:
            self.screenshot_count += 1
            filepath = self.output_dir / f"screenshot_{self.screenshot_count:04d}.png"
            screenshot.save(filepath)
        
        return screenshot
    
    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """
        Capture a specific region of the screen.
        
        Args:
            x: X-coordinate of the top-left corner
            y: Y-coordinate of the top-left corner
            width: Width of the region to capture
            height: Height of the region to capture
        
        Returns:
            PIL Image object containing the screenshot of the region
        """
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        
        if self.save_screenshots:
            self.screenshot_count += 1
            filepath = self.output_dir / f"screenshot_region_{self.screenshot_count:04d}.png"
            screenshot.save(filepath)
        
        return screenshot
    
    def get_screen_size(self) -> Tuple[int, int]:
        """
        Get the size of the screen.
        
        Returns:
            Tuple of (width, height) in pixels
        """
        return pyautogui.size()
