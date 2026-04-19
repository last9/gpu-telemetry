# Copyright (c) Last9, Inc.
"""Unit tests for the metric_names mapping module."""

from l9gpu.exporters.metric_names import (
    FIELD_DATA_POINT_ATTRIBUTES,
    FIELD_TO_OTEL_NAME,
    FIELD_UNITS,
    get_data_point_attributes,
    get_otel_name,
    get_unit,
)


class TestGetOtelName:
    def test_known_field_gpu_util(self) -> None:
        assert get_otel_name("gpu_util") == "gpu.utilization"

    def test_known_field_temperature(self) -> None:
        assert get_otel_name("temperature") == "gpu.temperature"

    def test_known_field_xgmi(self) -> None:
        assert get_otel_name("xgmi_link_bandwidth") == "gpu.interconnect.throughput"

    def test_known_field_ecc_per_block(self) -> None:
        assert get_otel_name("ecc_per_block") == "gpu.ecc.errors"

    def test_known_field_network_rx(self) -> None:
        assert get_otel_name("network_rx_bandwidth") == "gpu.interconnect.throughput"

    def test_unknown_field_uses_gpu_prefix(self) -> None:
        assert get_otel_name("unknown_field_xyz") == "gpu.unknown_field_xyz"

    def test_junction_temperature_maps_to_gpu_temperature(self) -> None:
        assert get_otel_name("junction_temperature") == "gpu.temperature"

    def test_hbm_temperature_maps_to_gpu_temperature(self) -> None:
        assert get_otel_name("hbm_temperature") == "gpu.temperature"

    def test_rows_replaced(self) -> None:
        assert get_otel_name("rows_replaced") == "gpu.row_remap.count"

    def test_retired_pages_single_bit(self) -> None:
        assert get_otel_name("retired_pages_count_single_bit") == "gpu.row_remap.count"

    def test_mem_util(self) -> None:
        assert get_otel_name("mem_util") == "gpu.memory.utilization"

    def test_ecc_volatile_correctable(self) -> None:
        assert get_otel_name("ecc_errors_volatile_correctable") == "gpu.ecc.errors"

    def test_ecc_volatile_uncorrectable(self) -> None:
        assert get_otel_name("ecc_errors_volatile_uncorrectable") == "gpu.ecc.errors"

    def test_throttle_reason(self) -> None:
        assert get_otel_name("throttle_reason") == "gpu.throttle.reason"

    def test_power_state(self) -> None:
        assert get_otel_name("power_state") == "gpu.power.state"

    def test_pcie_rx_bytes(self) -> None:
        assert get_otel_name("pcie_rx_bytes") == "gpu.pcie.throughput"

    def test_pcie_tx_bytes(self) -> None:
        assert get_otel_name("pcie_tx_bytes") == "gpu.pcie.throughput"

    def test_fan_speed_percent(self) -> None:
        assert get_otel_name("fan_speed_percent") == "gpu.fan.speed"


class TestGetUnit:
    def test_temperature_celsius(self) -> None:
        assert get_unit("temperature") == "Cel"

    def test_power_watts(self) -> None:
        assert get_unit("power_draw") == "W"

    def test_utilization_ratio(self) -> None:
        assert get_unit("gpu_util") == "1"

    def test_xgmi_bytes_per_sec(self) -> None:
        assert get_unit("xgmi_link_bandwidth") == "By/s"

    def test_ecc_errors(self) -> None:
        assert get_unit("ecc_per_block") == "{error}"

    def test_rows_replaced(self) -> None:
        assert get_unit("rows_replaced") == "{row}"

    def test_unknown_field_defaults_to_one(self) -> None:
        assert get_unit("some_unknown") == "1"

    def test_ecc_volatile_unit(self) -> None:
        assert get_unit("ecc_errors_volatile_correctable") == "{error}"

    def test_pcie_bytes_per_sec(self) -> None:
        assert get_unit("pcie_rx_bytes") == "By/s"

    def test_fan_speed_unit(self) -> None:
        assert get_unit("fan_speed_percent") == "1"

    def test_throttle_reason_unit(self) -> None:
        # throttle_reason is a bitmask of boolean flags; unit is the
        # UCUM-style "{bool}" annotation, not dimensionless "1".
        assert get_unit("throttle_reason") == "{bool}"


class TestGetDataPointAttributes:
    def test_temperature_has_sensor_edge(self) -> None:
        attrs = get_data_point_attributes("temperature")
        assert attrs == {"gpu.temperature.sensor": "edge"}

    def test_junction_temperature_has_sensor_hotspot(self) -> None:
        attrs = get_data_point_attributes("junction_temperature")
        assert attrs == {"gpu.temperature.sensor": "hotspot"}

    def test_hbm_temperature_has_sensor_memory(self) -> None:
        attrs = get_data_point_attributes("hbm_temperature")
        assert attrs == {"gpu.temperature.sensor": "memory"}

    def test_gpu_util_has_task_type_compute(self) -> None:
        attrs = get_data_point_attributes("gpu_util")
        assert attrs == {"gpu.task.type": "compute"}

    def test_mem_util_has_task_type_memory_controller(self) -> None:
        attrs = get_data_point_attributes("mem_util")
        assert attrs == {"gpu.task.type": "memory_controller"}

    def test_network_rx_has_direction(self) -> None:
        attrs = get_data_point_attributes("network_rx_bandwidth")
        assert attrs == {"gpu.interconnect.direction": "receive"}

    def test_network_tx_has_direction(self) -> None:
        attrs = get_data_point_attributes("network_tx_bandwidth")
        assert attrs == {"gpu.interconnect.direction": "transmit"}

    def test_xgmi_has_type(self) -> None:
        attrs = get_data_point_attributes("xgmi_link_bandwidth")
        assert attrs == {"gpu.interconnect.type": "xgmi"}

    def test_retired_single_bit_has_error_type(self) -> None:
        attrs = get_data_point_attributes("retired_pages_count_single_bit")
        assert attrs == {"gpu.ecc.error_type": "correctable"}

    def test_retired_double_bit_has_error_type(self) -> None:
        attrs = get_data_point_attributes("retired_pages_count_double_bit")
        assert attrs == {"gpu.ecc.error_type": "uncorrectable"}

    def test_unknown_field_returns_empty(self) -> None:
        assert get_data_point_attributes("some_unknown") == {}

    def test_ecc_volatile_correctable_attributes(self) -> None:
        attrs = get_data_point_attributes("ecc_errors_volatile_correctable")
        assert attrs == {
            "gpu.ecc.error_type": "correctable",
            "gpu.ecc.count_type": "volatile",
        }

    def test_ecc_volatile_uncorrectable_attributes(self) -> None:
        attrs = get_data_point_attributes("ecc_errors_volatile_uncorrectable")
        assert attrs == {
            "gpu.ecc.error_type": "uncorrectable",
            "gpu.ecc.count_type": "volatile",
        }

    def test_pcie_rx_has_direction_and_type(self) -> None:
        attrs = get_data_point_attributes("pcie_rx_bytes")
        assert attrs == {
            "gpu.interconnect.type": "pcie",
            "gpu.interconnect.direction": "receive",
        }

    def test_pcie_tx_has_direction_and_type(self) -> None:
        attrs = get_data_point_attributes("pcie_tx_bytes")
        assert attrs == {
            "gpu.interconnect.type": "pcie",
            "gpu.interconnect.direction": "transmit",
        }

    def test_returns_copy_not_reference(self) -> None:
        a = get_data_point_attributes("temperature")
        b = get_data_point_attributes("temperature")
        a["extra"] = "foo"
        assert "extra" not in b


class TestMappingConsistency:
    def test_all_unit_keys_have_otel_name(self) -> None:
        """Every field in FIELD_UNITS should also be in FIELD_TO_OTEL_NAME."""
        missing = set(FIELD_UNITS.keys()) - set(FIELD_TO_OTEL_NAME.keys())
        assert (
            missing == set()
        ), f"Fields in FIELD_UNITS but not FIELD_TO_OTEL_NAME: {missing}"

    def test_all_attribute_keys_have_otel_name(self) -> None:
        """Every field in FIELD_DATA_POINT_ATTRIBUTES should also be in FIELD_TO_OTEL_NAME."""
        missing = set(FIELD_DATA_POINT_ATTRIBUTES.keys()) - set(
            FIELD_TO_OTEL_NAME.keys()
        )
        assert (
            missing == set()
        ), f"Fields in FIELD_DATA_POINT_ATTRIBUTES but not FIELD_TO_OTEL_NAME: {missing}"
