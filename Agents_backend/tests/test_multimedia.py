import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add parent directory to sys.path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from Graph.agents.multimedia import _generate_image_openai_dalle

def test_generate_image_openai_dalle_default_model():
    """Verify default dall-e-3 generation."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "mock_key"}):
        mock_client = MagicMock()
        calls = []
        
        def mock_generate(**kwargs):
            calls.append(kwargs)
            mock_response = MagicMock()
            img_obj = MagicMock()
            img_obj.b64_json = None
            img_obj.url = "http://example.com/image.png"
            mock_response.data = [img_obj]
            return mock_response
            
        mock_client.images.generate = mock_generate
        
        with patch("openai.OpenAI", return_value=mock_client), \
             patch("urllib.request.urlopen") as mock_urlopen:
             
            mock_resp_obj = MagicMock()
            mock_resp_obj.read.return_value = b"fake_image_bytes"
            mock_urlopen.return_value.__enter__.return_value = mock_resp_obj
            
            result = _generate_image_openai_dalle("test prompt")
            
            assert result == b"fake_image_bytes"
            assert len(calls) == 1
            assert calls[0]["model"] == "dall-e-3"
            assert calls[0]["quality"] == "standard"

def test_generate_image_openai_dalle_custom_model():
    """Verify that custom model and size parameters are passed directly."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "mock_key"}):
        mock_client = MagicMock()
        calls = []
        
        def mock_generate(**kwargs):
            calls.append(kwargs)
            mock_response = MagicMock()
            img_obj = MagicMock()
            img_obj.b64_json = None
            img_obj.url = "http://example.com/image.png"
            mock_response.data = [img_obj]
            return mock_response
            
        mock_client.images.generate = mock_generate
        
        with patch("openai.OpenAI", return_value=mock_client), \
             patch("urllib.request.urlopen") as mock_urlopen:
             
            mock_resp_obj = MagicMock()
            mock_resp_obj.read.return_value = b"fake_image_bytes"
            mock_urlopen.return_value.__enter__.return_value = mock_resp_obj
            
            result = _generate_image_openai_dalle("test prompt", model="dall-e-2", size="1024x1024")
            
            assert result == b"fake_image_bytes"
            assert len(calls) == 1
            assert calls[0]["model"] == "dall-e-2"
            assert "quality" not in calls[0]

