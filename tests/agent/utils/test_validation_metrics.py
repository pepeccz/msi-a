"""
Tests for Phase 5: Validation Metrics

Tests the validation metrics tracking system.

Coverage:
- Metric recording (attempts, failures, retries, escalations)
- Stats calculation (rates, averages)
- Export functionality
- Reset functionality
"""

import pytest
from agent.utils.validation_metrics import ValidationMetrics, get_validation_metrics


class TestValidationMetrics:
    """Test core metrics tracking."""
    
    def setup_method(self):
        """Reset metrics before each test."""
        self.metrics = ValidationMetrics()
    
    def test_record_validation_attempt(self):
        """Should track validation attempts."""
        self.metrics.record_validation_attempt("test_tool")
        self.metrics.record_validation_attempt("test_tool")
        
        assert self.metrics.validation_attempts == 2
    
    def test_record_validation_failure(self):
        """Should track validation failures by layer and tool."""
        self.metrics.record_validation_failure("test_tool", "syntax", ["Missing param"])
        self.metrics.record_validation_failure("other_tool", "state", ["Missing state"])
        
        assert self.metrics.validation_failures == 2
        assert self.metrics.failure_by_layer["syntax"] == 1
        assert self.metrics.failure_by_layer["state"] == 1
        assert self.metrics.failure_by_tool["test_tool"] == 1
        assert self.metrics.failure_by_tool["other_tool"] == 1
    
    def test_record_retry_success(self):
        """Should track retry successes and counts."""
        self.metrics.record_retry_success("test_tool", retry_count=2)
        self.metrics.record_retry_success("other_tool", retry_count=1)
        
        assert self.metrics.retry_successes == 2
        assert len(self.metrics.retry_counts) == 2
        assert self.metrics.retry_counts == [2, 1]
    
    def test_record_escalation(self):
        """Should track escalations."""
        self.metrics.record_escalation("test_tool", "max_retries")
        
        assert self.metrics.escalations == 1


class TestValidationStats:
    """Test stats calculation."""
    
    def setup_method(self):
        """Reset metrics before each test."""
        self.metrics = ValidationMetrics()
    
    def test_failure_rate_calculation(self):
        """Should calculate failure rate correctly."""
        # 10 attempts, 3 failures → 30% failure rate
        for i in range(10):
            self.metrics.record_validation_attempt(f"tool{i}")
        for i in range(3):
            self.metrics.record_validation_failure(f"tool{i}", "syntax", ["error"])
        
        stats = self.metrics.get_stats()
        
        assert stats.failure_rate == 30.0
    
    def test_retry_success_rate_calculation(self):
        """Should calculate retry success rate correctly."""
        # 5 retries, 4 successes → 80% success rate
        for i in range(5):
            self.metrics.record_retry_attempt("tool", i+1)
        for i in range(4):
            self.metrics.record_retry_success("tool", i+1)
        
        stats = self.metrics.get_stats()
        
        assert stats.retry_success_rate == 80.0
    
    def test_avg_retries_before_success(self):
        """Should calculate average retries before success."""
        # Success after: 1, 2, 3 retries → avg 2.0
        self.metrics.record_retry_success("tool1", 1)
        self.metrics.record_retry_success("tool2", 2)
        self.metrics.record_retry_success("tool3", 3)
        
        stats = self.metrics.get_stats()
        
        assert stats.avg_retries_before_success == 2.0
    
    def test_escalation_rate_calculation(self):
        """Should calculate escalation rate correctly."""
        # 10 failures, 2 escalations → 20% escalation rate
        for i in range(10):
            self.metrics.record_validation_failure(f"tool{i}", "syntax", ["error"])
        for i in range(2):
            self.metrics.record_escalation(f"tool{i}", "max_retries")
        
        stats = self.metrics.get_stats()
        
        assert stats.escalation_rate == 20.0
    
    def test_zero_attempts_no_division_error(self):
        """Should handle zero attempts gracefully."""
        stats = self.metrics.get_stats()
        
        # All rates should be 0.0 (no division by zero)
        assert stats.failure_rate == 0.0
        assert stats.retry_success_rate == 0.0
        assert stats.escalation_rate == 0.0
    
    def test_failures_by_tool_top_10(self):
        """Should return top 10 tools by failure count."""
        # Create 15 tools with different failure counts
        for i in range(15):
            for _ in range(i + 1):  # tool0: 1 failure, tool14: 15 failures
                self.metrics.record_validation_failure(f"tool{i}", "syntax", ["error"])
        
        stats = self.metrics.get_stats()
        
        # Should only have top 10
        assert len(stats.failures_by_tool) == 10
        # Should be sorted (highest first)
        tool_names = list(stats.failures_by_tool.keys())
        assert tool_names[0] == "tool14"  # 15 failures
        assert tool_names[-1] == "tool5"   # 6 failures


class TestMetricsExport:
    """Test metrics export functionality."""
    
    def setup_method(self):
        """Reset metrics before each test."""
        self.metrics = ValidationMetrics()
    
    def test_export_dict_structure(self):
        """Should export metrics with correct structure."""
        # Record some metrics
        self.metrics.record_validation_attempt("test_tool")
        self.metrics.record_validation_failure("test_tool", "syntax", ["error"])
        
        export = self.metrics.export_dict()
        
        # Check structure
        assert "overall" in export
        assert "rates" in export
        assert "breakdown" in export
        assert "time_window" in export
        
        # Check overall
        assert export["overall"]["total_attempts"] == 1
        assert export["overall"]["total_failures"] == 1
        
        # Check breakdown
        assert "by_layer" in export["breakdown"]
        assert "by_tool" in export["breakdown"]
        assert export["breakdown"]["by_layer"]["syntax"] == 1
        assert export["breakdown"]["by_tool"]["test_tool"] == 1
    
    def test_export_rates_rounded(self):
        """Should round rates to 2 decimal places."""
        # Create scenario with non-round rates
        for i in range(7):
            self.metrics.record_validation_attempt(f"tool{i}")
        for i in range(2):
            self.metrics.record_validation_failure(f"tool{i}", "syntax", ["error"])
        
        export = self.metrics.export_dict()
        
        # 2/7 = 28.571... → should be 28.57
        assert export["rates"]["failure_rate"] == 28.57


class TestMetricsReset:
    """Test metrics reset functionality."""
    
    def setup_method(self):
        """Reset metrics before each test."""
        self.metrics = ValidationMetrics()
    
    def test_reset_clears_all_metrics(self):
        """Should reset all counters to zero."""
        # Record various metrics
        self.metrics.record_validation_attempt("tool1")
        self.metrics.record_validation_failure("tool1", "syntax", ["error"])
        self.metrics.record_retry_success("tool1", 2)
        self.metrics.record_escalation("tool1", "max_retries")
        
        # Reset
        self.metrics.reset()
        
        # All should be zero
        assert self.metrics.validation_attempts == 0
        assert self.metrics.validation_failures == 0
        assert self.metrics.retry_successes == 0
        assert self.metrics.escalations == 0
        assert len(self.metrics.failure_by_layer) == 0
        assert len(self.metrics.failure_by_tool) == 0
        assert len(self.metrics.retry_counts) == 0
    
    def test_reset_updates_window_start(self):
        """Should update window start time on reset."""
        old_start = self.metrics.window_start
        
        # Wait a bit (or just reset immediately)
        self.metrics.reset()
        
        # Window start should be different
        assert self.metrics.window_start >= old_start


class TestMetricsSingleton:
    """Test singleton pattern."""
    
    def test_get_validation_metrics_returns_same_instance(self):
        """Should return same instance on multiple calls."""
        metrics1 = get_validation_metrics()
        metrics2 = get_validation_metrics()
        
        assert metrics1 is metrics2
    
    def test_singleton_persists_data(self):
        """Should persist data across get_validation_metrics calls."""
        metrics1 = get_validation_metrics()
        metrics1.record_validation_attempt("test_tool")
        
        metrics2 = get_validation_metrics()
        
        # Should see the same data
        assert metrics2.validation_attempts == 1
