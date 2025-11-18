from __future__ import annotations

from typing import Iterable, List, Dict
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


_analyzer = SentimentIntensityAnalyzer()


def sentiment_score(text: str) -> float:
    """
    返回 VADER compound 分数（-1 ~ 1）
    """
    if not text:
        return 0.0
    vs = _analyzer.polarity_scores(text)
    return float(vs.get("compound", 0.0))


def score_texts(texts: Iterable[str]) -> List[float]:
    return [sentiment_score(t) for t in texts]



