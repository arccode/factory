// Copyright 2015 The Chromium OS Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package overlord

// Overlord server ports.
var (
	OverlordPort     = GetenvInt("OVERLORD_PORT", 4455)      // Socket server port
	OverlordLDPort   = GetenvInt("OVERLORD_LD_PORT", 4456)   // LAN discovery port
	OverlordHTTPPort = GetenvInt("OVERLORD_HTTP_PORT", 9000) // Overlord HTTP server port
)

const (
	pingTimeout = 10
)

// ConnServer Client mode
const (
	ModeNone = iota
	ModeControl
	ModeTerminal
	ModeShell
	ModeLogcat
	ModeFile
	ModeForward
)

// Logcat format
const (
	logcatTypeText = iota
	logcatTypeVT100
)

// RPC states
const (
	Success = "success"
	Failed  = "failed"
)

// Stream control
const (
	StdinClosed = "##STDIN_CLOSED##"
)

// ModeStr translate client mode to string.
func ModeStr(mode int) string {
	return map[int]string{
		ModeNone:     "None",
		ModeControl:  "Agent",
		ModeTerminal: "Terminal",
		ModeShell:    "Shell",
		ModeLogcat:   "Logcat",
		ModeFile:     "File",
		ModeForward:  "ModeForward",
	}[mode]
}

const (
	dutStatusIdle         = "idle"
	dutStatusRunning      = "running"
	dutStatusDisconnected = "disconnected"
	dutStatusFailed       = "failed"
)

// StatusScoreMapping maps the status to an integer for sorting.
func StatusScoreMapping(status string) int {
	return map[string]int{
		dutStatusIdle:         1,
		dutStatusRunning:      2,
		dutStatusDisconnected: 3,
		dutStatusFailed:       4,
		// For other status, map would return 0 for int type.
	}[status]
}
