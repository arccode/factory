# Test Data for Probe Info Service

Roughly, the major dataflow this service provides is:

1. Given probe info or overridden probe statement of components, the service
   converts them into a bundle file that contains all the corresponding probe
   statements.
2. The user invokes the bundle file to gain test results from real devices.
3. Given the test results, the service analyzes them and performs status
   changes.

The unittests cover both the stateless functionality of each single step,
as well as some common scenarios, which is constructed by a series of stateful
API calls.  Since both types of tests need test material like probe infos,
probe statements, test results, etc, this folder centralizes those data to
share across different test cases.

Most of the files in this folder follow a fixed naming convention:

```
  <data_type>-<id>-<variation>.<file_extension>
```

* `<data_type>` represents the kind of the test data.
* `<id>` is an index for cross referencing between testdata files.
* `<variation>` summaries the detail of the test data.
* `<file_extension>` is just the hint for the editor to choose the correct
  syntax parser.

For example, `component_probe_info-1-param_value_error.prototxt` contains a
`ComponentProbeInfo` protobuf message.  The message records the probe info of
an imagined qualification.  In addition, the probe info contains some wrong
values so the service should consider it invalid.

`probe_info_parsed_result-1-param_value_error.prototxt`, on the other hand,
contains the expected output the service should return from
`component_probe_info-1-param_value_error.prototxt`.
