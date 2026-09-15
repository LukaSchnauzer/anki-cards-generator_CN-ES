"""Anki model/note type definitions.

Un modelo (note type) distinto por nivel HSK y tipo de tarjeta —
ChinoSRS_SentenceCard_HSK3, ChinoSRS_SentenceCard_HSK4, etc. — en vez de un
solo modelo compartido entre niveles. Decisión explícita del usuario: deja
la puerta abierta a que el template/CSS diverja por nivel más adelante, a
costa de multiplicar modelos en Anki (3 tipos × N niveles).
"""

import os
from typing import List, Dict
from .api import post, model_exists, delete_model


def load_template(template_name: str) -> str:
    """Load HTML template from file."""
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", template_name)
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


# card_type (columna cards.card_type) -> mitad del nombre del modelo Anki.
CARD_TYPE_LABELS = {"sentence": "SentenceCard", "pattern": "PatternCard", "audio": "AudioCard"}


def model_name_for(card_type: str, hsk_level: int) -> str:
    """Nombre del modelo Anki para (card_type de la DB, nivel HSK), ej. 'sentence' + 3 -> 'ChinoSRS_SentenceCard_HSK3'."""
    return f"ChinoSRS_{CARD_TYPE_LABELS[card_type]}_HSK{hsk_level}"


def create_model_sentence(hsk_level: int, force_recreate: bool = False):
    """Create SentenceCard model for a given HSK level."""
    model_name = model_name_for("sentence", hsk_level)
    if force_recreate:
        delete_model(model_name)
    if model_exists(model_name):
        return

    fields = [
        "SortKey", "Hanzi", "HskLevel", "FreqBucket",
        "PrimaryPinyin", "PrimaryMeaningEs", "PrimaryMeaningZh",
        "ExampleZh", "ExampleEs",
        "BreakdownJson", "SecondariesJson", "CollocationsJson",
        "AudioWordFile", "AudioSentenceFile", "SentenceAlignmentJson",
    ]

    templates = [{
        "Name": model_name,
        "Front": load_template("sentence_card_front.html"),
        "Back": load_template("sentence_card_back.html")
    }]

    css = load_template("sentence_card.css")
    post("createModel", modelName=model_name, inOrderFields=fields, cardTemplates=templates, css=css)


def create_model_pattern(hsk_level: int, force_recreate: bool = False):
    """Create PatternCard model for a given HSK level."""
    model_name = model_name_for("pattern", hsk_level)
    if force_recreate:
        delete_model(model_name)
    if model_exists(model_name):
        return

    fields = [
        "SortKey", "Hanzi", "HskLevel", "FreqBucket",
        "PrimaryPinyin", "PrimaryMeaningEs", "PrimaryMeaningZh",
        "ExampleZh", "ExampleEs",
        "BreakdownJson", "SecondariesJson", "CollocationsJson",
        "AudioWordFile", "AudioSentenceFile", "SentenceAlignmentJson",
    ]

    templates = [{
        "Name": model_name,
        "Front": load_template("pattern_card_front.html"),
        "Back": load_template("pattern_card_back.html")
    }]

    css = load_template("pattern_card.css")
    post("createModel", modelName=model_name, inOrderFields=fields, cardTemplates=templates, css=css)


def create_model_audio(hsk_level: int, force_recreate: bool = False):
    """Create AudioCard model for a given HSK level."""
    model_name = model_name_for("audio", hsk_level)
    if force_recreate:
        delete_model(model_name)
    if model_exists(model_name):
        return

    fields = [
        "SortKey", "Hanzi", "HskLevel", "FreqBucket",
        "PrimaryPinyin", "PrimaryMeaningEs", "PrimaryMeaningZh",
        "ExampleZh", "ExampleEs",
        "BreakdownJson", "SecondariesJson", "CollocationsJson",
        "AudioWordFile", "AudioSentenceNormalFile", "AudioSentenceSlowFile",
        "SentenceAlignmentNormalJson", "SentenceAlignmentSlowJson",
    ]

    templates = [{
        "Name": model_name,
        "Front": load_template("audio_card_front.html"),
        "Back": load_template("audio_card_back.html")
    }]

    css = load_template("audio_card.css")
    post("createModel", modelName=model_name, inOrderFields=fields, cardTemplates=templates, css=css)


def setup_models(hsk_level: int, force_recreate: bool = False):
    """Set up the 3 ChinoSRS models for a given HSK level."""
    create_model_sentence(hsk_level, force_recreate)
    create_model_pattern(hsk_level, force_recreate)
    create_model_audio(hsk_level, force_recreate)
