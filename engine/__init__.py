"""MusicVidForge engine: audio analysis, visual templates and ffmpeg rendering."""

from .audio import TrackAnalyzer as TrackAnalyzer
from .render import render_video as render_video
from .templates import TEMPLATES as TEMPLATES
from .templates import register_templates as register_templates

__all__ = ["TrackAnalyzer", "TEMPLATES", "register_templates", "render_video"]
