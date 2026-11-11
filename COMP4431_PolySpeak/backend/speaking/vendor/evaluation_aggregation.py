# Pure aggregation methods copied from PolyInterview FinalEvaluationService.
from typing import Dict, Any

class PolyInterviewReportAggregation:

    def _aggregate_aspects(self, interview_log: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Aggregate aspects across all questions, calculating averages."""
        aspect_scores = {}
        aspect_justifications = {}
        for q in interview_log.get('questions', []):
            if q.get('category') == 'Candidate Questions':
                continue
            aspects = q.get('aspects', {})
            for key, data in aspects.items():
                if key not in aspect_scores:
                    aspect_scores[key] = []
                    aspect_justifications[key] = []
                if isinstance(data, dict) and 'score' in data:
                    aspect_scores[key].append(data['score'])
                    if data.get('justification'):
                        aspect_justifications[key].append(data['justification'])
        result = {}
        for key in aspect_scores:
            scores = aspect_scores[key]
            avg_score = sum(scores) / len(scores) if scores else 0
            result[key] = {'score': round(avg_score, 2), 'count': len(scores), 'justifications': aspect_justifications.get(key, [])}
        return result

    def _aggregate_features(self, interview_log: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Aggregate features across all questions, calculating averages."""
        feature_scores = {}
        for q in interview_log.get('questions', []):
            if q.get('category') == 'Candidate Questions':
                continue
            criteria = q.get('assessment_criteria', {})
            for category in ['professional_performance', 'way_of_expression', 'nonverbal', 'oral_expression']:
                cat_data = criteria.get(category, {})
                if not isinstance(cat_data, dict):
                    continue
                for key, data in cat_data.items():
                    if key in ['num_videos_evaluated', 'total_videos']:
                        continue
                    if key not in feature_scores:
                        feature_scores[key] = []
                    if isinstance(data, dict) and 'score' in data:
                        feature_scores[key].append(data['score'])
        result = {}
        for key in feature_scores:
            scores = feature_scores[key]
            avg_score = sum(scores) / len(scores) if scores else 0
            result[key] = {'score': round(avg_score, 2), 'count': len(scores)}
        return result
