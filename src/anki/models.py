"""Anki model/note type definitions."""

import os
from typing import List, Dict
from .api import post, model_exists, delete_model


def load_template(template_name: str) -> str:
    """Load HTML template from file."""
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", template_name)
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def create_model_sentence(force_recreate: bool = False):
    """Create SentenceCard model."""
    model_name = "ChinoSRS_SentenceCard"
    if force_recreate:
        delete_model(model_name)
    if model_exists(model_name):
        return

    fields = [
        "SortKey", "Hanzi", "Pinyin", "Meaning", "SentenceCN", "SentenceES",
        "Tips", "Collocations", "POS", "Register", "Frecuencia", "Tags", "Audio", "WordAudio",
        "FrontLine", "Hint1", "Hint2", "Hint3"
    ]
    
    templates = [{
        "Name": "ChinoSRS_SentenceCard",
        "Front": load_template("sentence_card_front.html"),
        "Back": load_template("sentence_card_back.html")
    }]
    
    css = ""
    post("createModel", modelName=model_name, inOrderFields=fields, cardTemplates=templates, css=css)


def create_model_pattern(force_recreate: bool = False):
    """Create PatternCard model."""
    model_name = "ChinoSRS_PatternCard"
    if force_recreate:
        delete_model(model_name)
    if model_exists(model_name):
        return

    fields = [
        "SortKey", "Hanzi", "Pinyin", "Meaning", "SentenceCN", "SentenceES", "Tips", "Pattern",
        "POS", "Register", "Frecuencia", "Audio", "WordAudio", "Tags",
        "ClozeSentence", "MissingPart", "Hint1", "Hint2", "Hint3", "Hint4"
    ]
    
    templates = [{
        "Name": "ChinoSRS_PatternCard",
        "Front": load_template("pattern_card_front.html"),
        "Back": load_template("pattern_card_back.html")
    }]
    
    css = ""
    post("createModel", modelName=model_name, inOrderFields=fields, cardTemplates=templates, css=css)


def create_model_audio(force_recreate: bool = False):
    """Create AudioCard model."""
    model_name = "ChinoSRS_AudioCard"
    if force_recreate:
        delete_model(model_name)
    if model_exists(model_name):
        return

    fields = [
        "SortKey", "Hanzi", "Pinyin", "Meaning", "SentenceCN", "SentenceES", "Tips",
        "POS", "Register", "Frecuencia", "Tags", "Audio", "WordAudio",
        "Hint1", "Hint2", "Hint3", "Hint4"
    ]
    
    templates = [{
        "Name": "ChinoSRS_AudioCard",
        "Front": load_template("audio_card_front.html"),
        "Back": load_template("audio_card_back.html")
    }]
    
    css = ""
    post("createModel", modelName=model_name, inOrderFields=fields, cardTemplates=templates, css=css)


def setup_models(force_recreate: bool = False):
    """Set up all Anki models."""
    create_model_sentence(force_recreate)
    create_model_pattern(force_recreate)
    create_model_audio(force_recreate)
