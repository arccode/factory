// Copyright 2015 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//
// Defines common functions of Apps.
//
// Automatically load clients from server in "compononetDidMount" event. The
// client list is fetched from @this.props.url and will be stored in
// @this.state.clients. But when rendering, you might want using
// @this.getFilteredClientList to remove all clients that should be hidden.
//
// Example:
//   var App = React.createClass({
//     mixins: [BaseApp],
//     getInitialState: function () {
//       return {...addtional_states};
//     },
//     componentWillMount: function () {
//       // You can register filters and handlers here.
//       // See @addOnNewClientHandler, @addClientFilter
//     },
//     componentDidMount: function () {
//       // loadClientsFromServer will be called after componentWillMount,
//       // before this function. You can, for example, create sockets in this
//       // method.
//     },
//     render: function () {
//       var clients = this.getFilteredClientList();
//       // render the UI using clients...
//     }
//   });

var BaseApp = {
  // A machine id filter, this filter is added to @this.state.clientFilters by
  // default, you can use @this.setMidFilterPattern to set the pattern used to
  // filter clients.
  //
  // for example:
  //   var onKeyUp = function (event) {
  //     this.setMidFilterPattern(this.refs.filter.value);
  //   };
  //   <input type="text" ref="filter" onKeyUp={onKeyUp} />
  _clientMidFilter: function (client) {
    if (typeof(this.state.midPattern) == "undefined") {
      return true;
    }
    return this.state.midPattern.test(client.mid);
  },
  _clientDisplayFilter: function (client) {
    if (typeof(this.state.displayPattern) == "undefined") {
      return true;
    }

    test_result = this.state.displayPattern.test(client.serial) ||
        this.state.displayPattern.test(client.status) ||
        this.state.displayPattern.test(client.pytest) ||
        this.state.displayPattern.test(client.model);
    return test_result;
  },
  getInitialState: function () {
    this.onNewClientHandlers = [];
    return {
      clients: [],
      midPattern: undefined,
      displayPattern: undefined,
      clientFilters: [this._clientMidFilter, this._clientDisplayFilter]
    };
  },
  componentDidMount: function () {
    this.loadClientsFromServer();
  },
  // Get a list of clients from @this.props.url, "propperties" of each client
  // would also be fetched through /api/agent/properties/ API. Each client
  // would be added to @this.state.clients by invoking @this.addClient API.
  // Use @this.addOnNewClientHandler to prevent adding uninteresting clients.
  loadClientsFromServer: function () {
    $.ajax({
      url: this.props.url,
      dataType: "json",
      success: function (data) {
        for (var i = 0; i < data.length; i++) {
          this.addClient(data[i]);
        }
      }.bind(this),
      error: function (xhr, status, err) {
        console.error(this.props.url, status, err.toString());
      }.bind(this)
    });
  },
  // Get "properties" of a client (defined by machine id) from server.  For
  // details about "properties" attribute of a client, please see
  // FixtureWidget.
  fetchProperties: function (mid, callback) {
    var url = "/api/agent/properties/" + mid;
    $.ajax({
      url: url,
      dataType: "json",
      success: callback,
      error: function (xhr, status, err) {
        console.error(url, status, err.toString());
      }.bind(this)
    });
  },
  clientCmp: function(client_a, client_b) {
    if (client_a.status_score != client_b.status_score) {
      return (client_a.status_score < client_b.status_score) ? 1 : -1;
    }
    return client_a.mid.localeCompare(client_b.mid)
  },
  // Adds a client to @this.state.clients, will call @this.fetchProperties to
  // get "properties" attribute of the client.
  // Will pass the client to each onNewClientHandler, if any handler returns
  // false, the client won't be added.
  addClient: function (client) {
    if (this.isClientInList(this.state.clients, client)) {
      return;
    }

    // TODO(pihsun): Don't fetch the properties again if it's already in client.
    this.fetchProperties(client.mid, function (properties) {
      client.properties = properties;

      if (this.isClientInList(this.state.clients, client)) {
        return;
      }

      for (var i = 0; i < this.onNewClientHandlers.length; i++) {
        if (!this.onNewClientHandlers[i](client)) {
          return;
        }
      }

      this.setState(function (state, props) {
        this.addClientToList(state.clients, client);
      });
    }.bind(this));
  },
  removeClient: function (data) {
    this.setState(function (state, props) {
      this.removeClientFromList(state.clients, data);
    });
  },
  updateClients: function (clients) {
    this.setState(function (state, unused_props) {
      for (var i = 0; i < state.clients.length; i++) {
        var index = clients.findIndex(function (el) {
          return el.mid == state.clients[i].mid;
        });
        if (index !== -1) {
          // Inherit properties first.
          clients[index].properties = state.clients[i].properties;
          // Then update info into state.
          state.clients[i] = clients[index];
        }
      }
      state.clients.sort(this.clientCmp);
    });
  },
  // Add a hook to @this.addClient, when a client is going to be added to
  // @this.state.clients, handlers will be invoke to determine whether we
  // should abort the action or not, the client that is going to be added
  // would be passed to each handler, if any handler returns false, the
  // client won't be added. The client will have "properties" attribute.
  addOnNewClientHandler: function (callback) {
    if (this.onNewClientHandlers.indexOf(callback) === -1) {
      this.onNewClientHandlers.push(callback);
    }
  },
  // If a handler previously added by @this.addOnNewClientHandler is not an
  // anonymous function, you can use this function to remove it from the
  // list.
  removeOnNewClientHandler: function (callback) {
    var index = this.onNewClientHandlers.indexOf(callback);
    if (index !== -1) {
      this.onNewClientHandlers.splice(index, 1);
    }
  },
  // add a filter to determine which clients should not be shown, the
  // function @this.getFilteredClientList will pass each client to each
  // filter, if any filter returns false, that client will be filtered out.
  addClientFilter: function (filter) {
    this.setState(function (state, props) {
      if (state.clientFilters.indexOf(filter) === -1) {
        state.clientFilters.push(filter);
      }
    });
  },
  // If a filter previously added by @this.addClientFilter is not an
  // anonymous function, you can use this function to remove it from the
  // list.
  removeClientFilter: function (filter) {
    var index = this.state.clientFilters.indexOf(filter);
    if (index !== -1) {
      this.state.clientFilters.splice(index, 1);
    }
  },
  // Pass each element in @this.state.clients to each filter registered by
  // @this.addClientFilter, if any filter returns false, that client will not
  // be returned.
  getFilteredClientList: function () {
    var filteredList = this.state.clients.slice();
    for (var i = 0; i < this.state.clientFilters.length; i++) {
      filteredList = filteredList.filter(this.state.clientFilters[i]);
    }
    return filteredList;
  },
  getRuntimeClient: function(mid) {
    var index = this.state.clients.findIndex(function (el) {
      return el.mid == mid;
    });
    if (index !== -1) {
      return this.state.clients[index];
    }
  },
  // See @this._clientMidFilter.
  setMidFilterPattern: function (pattern) {
    if (typeof(pattern) != "undefined") {
      this.setState({midPattern: new RegExp(pattern, "i")});
    }
  },
  // See @this._clientDisplayFilter.
  setDisplayFilterPattern: function (pattern) {
    if (typeof(pattern) != "undefined") {
      this.setState({displayPattern: new RegExp(pattern, "i")});
    }
  },
  isClientInList: function (target_list, client) {
    return target_list.some(function (el) {
      return el.mid == client.mid;
    });
  },
  addClientToList: function (target_list, obj) {
    target_list.push(obj);
    target_list.sort(this.clientCmp);
  },
  removeClientFromList: function (target_list, obj) {
    var index = target_list.findIndex(function (el) {
      return el.mid == obj.mid;
    });
    if (index !== -1) {
      target_list.splice(index, 1);
    }
    return target_list;
  },
  renderText: function (text, add_tooltip = true, capitalize = false) {
    var color = "black";

    switch (text) {
      case "running":
        color = "green";
        break;
      case "failed":
        color = "red";
        break;
      case "idle":
        color = "blue";
        break;
      case "disconnected":
        color = "gray";
        break;
    }

    if (capitalize) {
      text = text.charAt(0).toUpperCase() + text.slice(1);
    }

    if (add_tooltip) {
      return (<font color={color} data-toggle="tooltip" title={text}>{text}</font>);
    }

    return (<font color={color}>{text}</font>);
  },
};
