"""Centralized Rich console instance with purple theme configuration."""

from rich.console import Console
from rich.theme import Theme

# Purple-themed color palette
purple_theme = Theme({
    "primary": "#8B5CF6",      # Violet-500 - Headers, titles, primary actions
    "accent": "#A855F7",       # Purple-500 - Highlights, emphasis, interactive elements
    "muted": "#C4B5FD",        # Violet-300 - Secondary text, subdued information
    "bright": "#DDD6FE",       # Violet-200 - Backgrounds, subtle highlights
    "success": "#10B981",      # Emerald-500 - Success messages, completed actions
    "error": "#EF4444",        # Red-500 - Error messages, failures
    "warning": "#F59E0B",      # Amber-500 - Warnings, cautions
    "info": "#6366F1",         # Indigo-500 - Information, help text
})

# Global console instance with purple theme
console = Console(theme=purple_theme, highlight=False)