"""
FRED 데이터 검증 모듈
- 이상치(outlier) 감지
- 데이터 누락 시 처리
- 데이터 품질 검증
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """데이터 검증 오류"""
    pass


class DataQualityIssue:
    """데이터 품질 이슈 정보"""
    def __init__(self, issue_type: str, severity: str, message: str, affected_dates: Optional[List[date]] = None):
        self.issue_type = issue_type  # 'outlier', 'missing', 'quality'
        self.severity = severity  # 'critical', 'warning', 'info'
        self.message = message
        self.affected_dates = affected_dates or []
    
    def to_dict(self):
        return {
            'issue_type': self.issue_type,
            'severity': self.severity,
            'message': self.message,
            'affected_dates': [d.strftime('%Y-%m-%d') if isinstance(d, date) else str(d) for d in self.affected_dates]
        }


class FREDDataValidator:
    """FRED 데이터 검증 클래스"""
    
    def __init__(self):
        # 각 지표별 정상 범위 정의 (지표 코드 -> (min, max))
        self.indicator_ranges = {
            "DGS10": (0.0, 20.0),  # 10년 국채 금리: 0~20%
            "DGS2": (0.0, 20.0),   # 2년 국채 금리: 0~20%
            "FEDFUNDS": (0.0, 20.0),  # 연준 금리: 0~20%
            "CPIAUCSL": (50.0, 500.0),  # CPI 지수: 50~500
            "PCEPI": (50.0, 500.0),  # PCE 지수: 50~500
            "GDP": (0.0, 50000.0),  # GDP: 0~50조 달러
            "UNRATE": (0.0, 30.0),  # 실업률: 0~30%
            "PAYEMS": (50000.0, 200000.0),  # 비농업 고용: 5천만~2억명
            "WALCL": (0.0, 15000000.0),  # 연준 총자산: 0~1.5조 달러
            "WTREGEN": (0.0, 1000000.0),  # TGA: 0~1조 달러
            "RRPONTSYD": (0.0, 5000000.0),  # RRP: 0~5천억 달러
            "BAMLH0A0HYM2": (0.0, 30.0),  # 하이일드 스프레드: 0~30%
        }
        
        # 이상치 감지 방법 설정
        self.outlier_method = 'iqr'  # 'iqr' 또는 'zscore'
        self.zscore_threshold = 3.0  # Z-score 임계값
        self.iqr_multiplier = 1.5  # IQR 배수
    
    def validate_data_quality(
        self,
        indicator_code: str,
        data: pd.Series,
        check_outliers: bool = True,
        check_missing: bool = True,
        check_range: bool = True
    ) -> List[DataQualityIssue]:
        """
        데이터 품질 검증
        
        Args:
            indicator_code: 지표 코드
            data: 시계열 데이터
            check_outliers: 이상치 검사 여부
            check_missing: 누락 데이터 검사 여부
            check_range: 범위 검사 여부
            
        Returns:
            List[DataQualityIssue]: 발견된 품질 이슈 목록
        """
        issues = []
        
        if data is None or len(data) == 0:
            issues.append(DataQualityIssue(
                issue_type='missing',
                severity='critical',
                message=f'{indicator_code}: 데이터가 없습니다.'
            ))
            return issues
        
        # 범위 검사
        if check_range:
            range_issues = self._check_value_range(indicator_code, data)
            issues.extend(range_issues)
        
        # 누락 데이터 검사
        if check_missing:
            missing_issues = self._check_missing_data(indicator_code, data)
            issues.extend(missing_issues)
        
        # 이상치 검사
        if check_outliers:
            outlier_issues = self._detect_outliers(indicator_code, data)
            issues.extend(outlier_issues)
        
        return issues
    
    def _check_value_range(self, indicator_code: str, data: pd.Series) -> List[DataQualityIssue]:
        """값 범위 검사"""
        issues = []
        
        if indicator_code not in self.indicator_ranges:
            return issues
        
        min_val, max_val = self.indicator_ranges[indicator_code]
        out_of_range = data[(data < min_val) | (data > max_val)]
        
        if len(out_of_range) > 0:
            affected_dates = [idx.date() if isinstance(idx, pd.Timestamp) else idx for idx in out_of_range.index]
            issues.append(DataQualityIssue(
                issue_type='quality',
                severity='critical' if len(out_of_range) > len(data) * 0.1 else 'warning',
                message=f'{indicator_code}: {len(out_of_range)}개 데이터 포인트가 정상 범위({min_val}~{max_val})를 벗어났습니다.',
                affected_dates=affected_dates
            ))
        
        return issues
    
    def _check_missing_data(self, indicator_code: str, data: pd.Series) -> List[DataQualityIssue]:
        """누락 데이터 검사"""
        issues = []
        
        # NaN 값 확인
        nan_count = data.isna().sum()
        if nan_count > 0:
            nan_dates = [idx.date() if isinstance(idx, pd.Timestamp) else idx 
                        for idx in data[data.isna()].index]
            issues.append(DataQualityIssue(
                issue_type='missing',
                severity='warning' if nan_count < len(data) * 0.1 else 'critical',
                message=f'{indicator_code}: {nan_count}개 NaN 값이 발견되었습니다.',
                affected_dates=nan_dates
            ))
        
        # 연속된 누락 데이터 확인 (gap detection)
        if len(data) > 1:
            gaps = self._detect_data_gaps(data)
            if gaps:
                issues.append(DataQualityIssue(
                    issue_type='missing',
                    severity='warning' if len(gaps) < 5 else 'critical',
                    message=f'{indicator_code}: {len(gaps)}개의 데이터 갭이 발견되었습니다.',
                    affected_dates=gaps
                ))
        
        return issues
    
    def _detect_data_gaps(self, data: pd.Series) -> List[date]:
        """데이터 갭 감지 (연속된 날짜에서 누락된 날짜 찾기)"""
        gaps = []
        
        if len(data) < 2:
            return gaps
        
        # 날짜 인덱스를 정렬
        sorted_dates = sorted(data.index)
        
        for i in range(len(sorted_dates) - 1):
            current_date = sorted_dates[i]
            next_date = sorted_dates[i + 1]
            
            # 날짜 차이 계산
            if isinstance(current_date, pd.Timestamp):
                current = current_date.date()
            else:
                current = current_date
            
            if isinstance(next_date, pd.Timestamp):
                next_d = next_date.date()
            else:
                next_d = next_date
            
            days_diff = (next_d - current).days
            
            # 일별 데이터인 경우 1일 이상 차이나면 갭으로 간주
            # 주별 데이터인 경우 7일 이상 차이나면 갭으로 간주
            # 월별 데이터인 경우 35일 이상 차이나면 갭으로 간주
            if days_diff > 1:
                # 갭 사이의 날짜들을 추가
                for gap_day in range(1, days_diff):
                    gap_date = current + timedelta(days=gap_day)
                    gaps.append(gap_date)
        
        return gaps
    
    def _detect_outliers(self, indicator_code: str, data: pd.Series) -> List[DataQualityIssue]:
        """이상치 감지"""
        issues = []
        
        if len(data) < 10:  # 데이터가 너무 적으면 이상치 검사 스킵
            return issues
        
        # NaN 제거
        clean_data = data.dropna()
        if len(clean_data) < 10:
            return issues
        
        outliers = []
        
        if self.outlier_method == 'iqr':
            outliers = self._detect_outliers_iqr(clean_data)
        elif self.outlier_method == 'zscore':
            outliers = self._detect_outliers_zscore(clean_data)
        
        if len(outliers) > 0:
            affected_dates = [idx.date() if isinstance(idx, pd.Timestamp) else idx 
                            for idx in outliers.index]
            
            # 이상치 비율에 따라 심각도 결정
            outlier_ratio = len(outliers) / len(clean_data)
            severity = 'critical' if outlier_ratio > 0.1 else 'warning'
            
            issues.append(DataQualityIssue(
                issue_type='outlier',
                severity=severity,
                message=f'{indicator_code}: {len(outliers)}개 이상치가 발견되었습니다. (전체의 {outlier_ratio*100:.1f}%)',
                affected_dates=affected_dates
            ))
        
        return issues
    
    def _detect_outliers_iqr(self, data: pd.Series) -> pd.Series:
        """IQR 방법으로 이상치 감지"""
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - self.iqr_multiplier * IQR
        upper_bound = Q3 + self.iqr_multiplier * IQR
        
        outliers = data[(data < lower_bound) | (data > upper_bound)]
        return outliers
    
    def _detect_outliers_zscore(self, data: pd.Series) -> pd.Series:
        """Z-score 방법으로 이상치 감지"""
        mean = data.mean()
        std = data.std()
        
        if std == 0:
            return pd.Series(dtype=float)
        
        z_scores = np.abs((data - mean) / std)
        outliers = data[z_scores > self.zscore_threshold]
        return outliers
    
    def handle_missing_data(
        self,
        data: pd.Series,
        method: str = 'forward_fill'
    ) -> pd.Series:
        """
        누락 데이터 처리
        
        Args:
            data: 시계열 데이터
            method: 처리 방법 ('forward_fill', 'backward_fill', 'interpolate', 'drop')
            
        Returns:
            pd.Series: 처리된 데이터
        """
        if method == 'forward_fill':
            return data.fillna(method='ffill')
        elif method == 'backward_fill':
            return data.fillna(method='bfill')
        elif method == 'interpolate':
            return data.interpolate(method='linear')
        elif method == 'drop':
            return data.dropna()
        else:
            logger.warning(f"알 수 없는 처리 방법: {method}. forward_fill을 사용합니다.")
            return data.fillna(method='ffill')
    
    def get_data_quality_summary(
        self,
        indicator_code: str,
        data: pd.Series
    ) -> Dict:
        """
        데이터 품질 요약 정보 반환
        
        Args:
            indicator_code: 지표 코드
            data: 시계열 데이터
            
        Returns:
            Dict: 품질 요약 정보
        """
        if data is None or len(data) == 0:
            return {
                'indicator_code': indicator_code,
                'status': 'error',
                'message': '데이터가 없습니다.',
                'data_points': 0,
                'issues': []
            }
        
        issues = self.validate_data_quality(indicator_code, data)
        
        # 심각도별 이슈 개수
        critical_count = sum(1 for issue in issues if issue.severity == 'critical')
        warning_count = sum(1 for issue in issues if issue.severity == 'warning')
        
        # 전체 상태 결정
        if critical_count > 0:
            status = 'critical'
        elif warning_count > 0:
            status = 'warning'
        else:
            status = 'ok'
        
        # numpy 타입을 Python 기본 타입으로 변환
        missing_count = data.isna().sum()
        if hasattr(missing_count, 'item'):
            missing_count = int(missing_count.item())
        else:
            missing_count = int(missing_count)
        
        return {
            'indicator_code': indicator_code,
            'status': status,
            'data_points': int(len(data)),
            'missing_count': missing_count,
            'critical_issues': int(critical_count),
            'warning_issues': int(warning_count),
            'issues': [issue.to_dict() for issue in issues]
        }

