// Copyright 2015 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Requires:
//   NavBar.jsx :: NavBar
//   UploadProgressWidget.jsx :: UploadProgressWidget
//   FixtureWidget.jsx :: FixtureWidget
//   TerminalWindow.jsx :: TerminalWindow
//   CameraWindow.jsx :: CameraWindow
//
// View for Dashboard App:
// - App
//  - NavBar
//  - SideBar
//   - ClientBox
//    - FilterInput
//    - ClientList
//     - [ClientInfo ...]
//    - RecentList
//     - ClientInfo
//  - Windows
//   - [TerminalWindow ...]
//   - [CameraWindow ...]
//   - UploadProgressWidget
//  - FixtureGroup
//   - [FixtureWidget ...]

var App = React.createClass({
  mixins: [BaseApp],
  addTerminal: function (id, term) {
    this.setState(function (state, props) {
      state.terminals[id] = term;
    });
  },
  addFixture: function (client) {
    if (this.isClientInList(this.state.fixtures, client)) {
      return;
    }

    // only keep recently opened @nTotalFixture fixtures.
    var nTotalFixture = 2;
    this.setState(function (state, props) {
      state.fixtures.push(client);
      return {fixtures: state.fixtures.slice(-nTotalFixture)};
    });
  },
  addCamera: function (id, cam) {
    this.setState(function (state, props) {
      state.cameras[id] = cam;
    });
  },
  toggleFixtureState: function (client) {
    if (this.isClientInList(this.state.fixtures, client)) {
      this.removeFixture(client.mid);
    } else {
      this.addFixture(client);
    }
  },
  removeTerminal: function (id) {
    this.setState(function (state, props) {
      if (typeof(state.terminals[id]) != "undefined") {
        delete state.terminals[id];
      }
    });
  },
  removeFixture: function (id) {
    this.setState(function (state, props) {
      this.removeClientFromList(state.fixtures, {mid: id});
    });
  },
  removeCamera: function (id) {
    this.setState(function (state, props) {
      if (typeof(state.cameras[id]) != "undefined") {
        delete state.cameras[id];
      }
    });
  },
  getInitialState: function () {
    return {cameras: [], fixtures: [], terminals: {}};
  },
  componentDidMount: function () {
    var socket = io(window.location.protocol + "//" + window.location.host,
                    {path: "/api/socket.io/"});
    this.socket = socket;

    socket.on("agent joined", function (msg) {
      var client = JSON.parse(msg);
      this.addClient(client);
    }.bind(this));

    socket.on("agent left", function (msg) {
      var client = JSON.parse(msg);

      this.removeClientFromList(this.state.clients, client);
      this.removeFixture(client.mid);
    }.bind(this));

    socket.on("agent update", function (msg) {
      var clients = JSON.parse(msg);
      this.updateClients(clients);
    }.bind(this));

    // Initiate a file download
    socket.on("file download", function (sid) {
      var url = window.location.protocol + "//" + window.location.host +
                "/api/file/download/" + sid;
      $("<iframe src='" + url + "' style='display:none'>" +
        "</iframe>").appendTo('body');
    });
  },
  render: function () {
    return (
      <div id="main">
        <NavBar name="Dashboard" url="/api/apps/list" ref="navbar" />
        <div id="container">
          <SideBar clients={this.getFilteredClientList()} ref="sidebar" app={this} />
          <FixtureGroup fixtures={this.state.fixtures} app={this}
           uploadProgress={this.refs.uploadProgress} />
        </div>
        <div className="windows">
          <Windows app={this} terminals={this.state.terminals}
           uploadProgress={this.refs.uploadProgress}
           cameras={this.state.cameras} />
        </div>
        <div className="upload-progress">
          <UploadProgressWidget ref="uploadProgress" />
        </div>
      </div>
    );
  }
});

var SideBar = React.createClass({
  render: function () {
    return (
      <div className="sidebar">
        <OverallStatus clients={this.props.clients} app={this.props.app} />
        <ClientBox clients={this.props.clients} app={this.props.app} />
      </div>
    );
  }
});

var OverallStatus = React.createClass({
  render: function () {
    return (
      <div className="overall-status panel panel-success">
        <div className="panel-heading">Overall Status</div>
        <div className="panel-body">
          <StatusTable clients={this.props.clients} app={this.props.app} />
        </div>
      </div>
    );
  }
})

var StatusTable = React.createClass({
  render: function () {
    var headers = ["total", "running", "failed", "idle", "disconnected"];
    return (
      <table className="status-table">
        <thead>
          <tr>
          {
            headers.map(function (name) {
              return (
                <th className="table-cell-common">
                  {this.props.app.renderText(name, false, true)}
                </th>
              );
            }.bind(this))
          }
          </tr>
        </thead>
        <tbody>
          <td className="table-cell-common">
            {this.props.clients.filter(client => client.mid!="host").length}
          </td>
          {
            headers.slice(1).map(function (name) {
              return (
                <td className="table-cell-common">
                  {this.props.clients.filter(client => client.status==name).length}
                </td>
              );
            }.bind(this))
          }
        </tbody>
      </table>
    );
  }
});

var ClientBox = React.createClass({
  render: function () {
    return (
      <div className="client-box panel panel-success">
        <div className="panel-heading">Clients</div>
        <div className="panel-body">
          <FilterInput app={this.props.app} />
          <ClientTable clients={this.props.clients} app={this.props.app} />
        </div>
      </div>
    );
  }
})

var FilterInput = React.createClass({
  onKeyUp: function (event) {
    this.props.app.setDisplayFilterPattern(this.refs.filter.value);
  },
  render: function () {
    return (
      <div>
        <input type="text" className="filter-input form-control" ref="filter"
            placeholder="keyword" onKeyUp={this.onKeyUp}></input>
      </div>
    )
  }
});

var ClientTable = React.createClass({
  render: function () {
    var headers = ["model", "serial", "status", "pytest", "manage"];
    return (
      <table className="client-table">
        <thead>
          <tr>
          {
            headers.map(function (name) {
              return (
                <th className={"table-" + name + "-col table-cell-common"}>
                  {this.props.app.renderText(name, false, true)}
                </th>
              );
            }.bind(this))
          }
          </tr>
        </thead>
        <tbody>
        {
          this.props.clients.map(function (client) {
            if (client.mid == "host") {
              return null;
            }
            return (
              <ClientRow client={client} app={this.props.app} headers={headers}></ClientRow>
            );
          }.bind(this))
        }
        </tbody>
      </table>
    );
  }
});

var ClientRow = React.createClass({
  openTerminal: function (event) {
    this.props.app.addTerminal(randomID(), this.props.client);
  },
  onManageBtnClick: function (event) {
    this.props.app.toggleFixtureState(this.props.client);
  },
  getManageSpan: function() {
    var manage_span = null;

    if (this.props.client.status == "disconnected") {
      return manage_span;
    }

    if (typeof(this.props.client.properties) != "undefined" &&
        typeof(this.props.client.properties.context) != "undefined" &&
        this.props.client.properties.context.indexOf("ui") !== -1) {
      var ui_state = this.props.app.isClientInList(
          this.props.app.state.fixtures, this.props.client);
      var ui_light_css = LIGHT_CSS_MAP[ui_state ? "light-toggle-on"
                                                : "light-toggle-off"];
      manage_span = (
        <div className={"label " + ui_light_css + " client-info-button"}
            data-mid={this.props.client.key} onClick={this.onManageBtnClick}>
          Manage
        </div>
      );
    }

    return manage_span;
  },
  render: function () {
    return (
      <tr>
      {
        this.props.headers.map(function (name) {
          var span = null;
          if (name == "manage") {
            span = this.getManageSpan();
          } else {
            span = this.props.app.renderText(this.props.client[name]);
          }

          return (
            <td className={"table-" + name + "-col table-cell-common"}>
              {span}
            </td>
          );
        }.bind(this))
      }
      </tr>
    )
  }
});

var Windows = React.createClass({
  render: function () {
    var onTerminalControl = function (control) {
      if (control.type == "sid") {
        this.terminal_sid = control.data;
        this.props.app.socket.emit("subscribe", control.data);
      }
    };
    var onTerminalCloseClicked = function (event) {
      this.props.app.removeTerminal(this.props.id);
      this.props.app.socket.emit("unsubscribe", this.terminal_sid);
    };
    var onCameraCloseClicked = function (event) {
      this.props.app.removeCamera(this.props.id);
    }
    // We need to make TerminalWindow and CameraWindow have the same parent
    // div so z-index stacking works.
    return (
      <div>
        <div className="windows">
          {
            Object.keys(this.props.terminals).map(function (id) {
              var term = this.props.terminals[id];
              var extra = "";
              if (typeof(term.path) != "undefined") {
                extra = "?tty_device=" + term.path;
              }
              return (
                <TerminalWindow key={id} mid={term.mid} id={id} title={term.mid}
                 path={"/api/agent/tty/" + term.mid + extra}
                 uploadRequestPath={"/api/agent/upload/" + term.mid}
                 enableMaximize={true}
                 app={this.props.app} progressBars={this.props.uploadProgress}
                 onControl={onTerminalControl}
                 onCloseClicked={onTerminalCloseClicked} />
              );
            }.bind(this))
          }
          {
            Object.keys(this.props.cameras).map(function (id) {
              var cam = this.props.cameras[id];
              var cam_prop = cam.properties.camera;
              if (typeof(cam_prop) != "undefined") {
                var command = cam_prop.command;
                var width = cam_prop.width || 640;
                var height = cam_prop.height || 640;
                return (
                    <CameraWindow key={id} mid={cam.mid} id={id} title={cam.mid}
                     path={"/api/agent/shell/" + cam.mid + "?command=" +
                           encodeURIComponent(command)}
                     width={width} height={height} app={this.props.app}
                     onCloseClicked={onCameraCloseClicked} />
                );
              }
            }.bind(this))
          }
        </div>
      </div>
    );
  }
});

var FixtureGroup = React.createClass({
  render: function () {
    var overlord_host = this.props.app.getRuntimeClient('host');
    var ovl_path = "";
    var certificate_dir = "";
    if (typeof(overlord_host) != "undefined" &&
        typeof(overlord_host.properties.ovl_path) != "undefined" &&
        typeof(overlord_host.properties.certificate_dir) != "undefined") {
      ovl_path = overlord_host.properties.ovl_path;
      certificate_dir = overlord_host.properties.certificate_dir;
    }
    return (
      <div className="fixture-group">
        {
          this.props.fixtures.map(function (fixture) {
            return (
              <FixtureWidget key={fixture.mid}
               client={this.props.app.getRuntimeClient(fixture.mid)}
               progressBars={this.props.uploadProgress}
               app={this.props.app}
               ovl_path={ovl_path} certificate_dir={certificate_dir}
               width='45%' />
            );
          }.bind(this))
        }
      </div>
    );
  }
});

ReactDOM.render(
  <App url="/api/agents/list" />,
  document.getElementById("body")
);
