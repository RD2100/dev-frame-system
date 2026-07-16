//go:build !windows

package server

import (
	"net"
)

func NewListener(spec ListenerSpec) (net.Listener, error) {
	return net.Listen("tcp", spec.Addr)
}
