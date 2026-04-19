---
sidebar_position: 7
---

# Adding New Exporter

l9gpu supports multiple [exporters](https://github.com/last9/gpu-telemetry/tree/main/l9gpu/exporters), each one is responsible for exporting data to a different destination. To add a new exporter, you'll need to:

1. Create a file for the new exporter on the [exporters](https://github.com/last9/gpu-telemetry/tree/main/l9gpu/exporters) folder.

See existing [exporters](https://github.com/last9/gpu-telemetry/tree/main/l9gpu/exporters) and choose an appropriate name for the new exporter.

2. Create the exporter class.

Some important things when creating a new exporter class:

1. `@register("<your_exporter_name>")` decorator.

This decorator registers the exporter with l9gpu, so you should be able to call it from the CLI with the `--sink` option:

```
l9gpu ... --sink=<your_exporter_name> ...
```

2. Arguments to `__init__` method.

If you want to send exporter specific arguments at CLI invocation time (or provide them via config files), you can add them to the `__init__` method. For example, if you want to send a `port` argument to the exporter, you can add it to the `__init__` method like this:

```
def __init__(self, *, port: Optional[int] = None) -> None:
    ...
```

Then you'll be able to call the CLI and send a `port`:

```
l9gpu ... --sink=<your_exporter_name> -o port=9000 ...
```

3. Implement the `write` method.

This method is responsible for exporting the data to the destination. It receives a [`Log`](https://github.com/last9/gpu-telemetry/blob/main/l9gpu/schemas/log.py) object and a [`SinkAdditionalParams`](https://github.com/last9/gpu-telemetry/blob/main/l9gpu/monitoring/sink/protocol.py) object.

`Log` contains the data to be exported as an iterator of dataclasses.

`SinkAdditionalParams` has a `data_type` field that tells the exporter if it should treat the data as a [LOG](https://github.com/last9/gpu-telemetry/blob/main/l9gpu/monitoring/sink/protocol.py) or [METRIC](https://github.com/last9/gpu-telemetry/blob/main/l9gpu/monitoring/sink/protocol.py), see [Telemetry types supported by l9gpu](telemetry_types.md):

- This is defined at collection time
- These are commonly used to treat data differently at export time, if needed

To see a real implementation of a simple exporter class and its write method, you can see the stdout exporter [here](https://github.com/last9/gpu-telemetry/blob/main/l9gpu/exporters/stdout.py).

After you've completed this step, you should be able to test calling your new exporter from the CLI:

```
l9gpu ... --sink=<your_exporter_name> ... # add the following for any required exporter args: -o key=value
```
