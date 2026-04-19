// Copyright (c) Meta Platforms, Inc. and affiliates.
// Modifications by Last9, Inc.
// Copyright (c) Last9, Inc.
// All rights reserved.
package slurmprocessor

import (
	"path"
	"testing"

	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/collector/component"
	"go.opentelemetry.io/collector/exporter"
	"go.opentelemetry.io/collector/exporter/exportertest"
	"go.opentelemetry.io/collector/otelcol"
	"go.opentelemetry.io/collector/otelcol/otelcoltest"
	"go.opentelemetry.io/collector/processor"
	"go.opentelemetry.io/collector/receiver"
	"go.opentelemetry.io/collector/receiver/receivertest"
)

func TestLoadConfig(t *testing.T) {
	factories := otelcol.Factories{
		Receivers: map[component.Type]receiver.Factory{
			component.MustNewType("nop"): receivertest.NewNopFactory(),
		},
		Processors: map[component.Type]processor.Factory{
			component.MustNewType("slurm"): NewFactory(),
		},
		Exporters: map[component.Type]exporter.Factory{
			component.MustNewType("nop"): exportertest.NewNopFactory(),
		},
	}

	cfg, err := otelcoltest.LoadConfigAndValidate(path.Join(".", "testdata", "config.yaml"), factories)
	require.NoError(t, err)
	require.NotNil(t, cfg)
}
