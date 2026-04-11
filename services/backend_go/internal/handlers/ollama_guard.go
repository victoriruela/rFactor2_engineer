package handlers

import (
	"net"
	"net/url"
	"strings"
)

func normalizeProvider(provider string) string {
	if strings.TrimSpace(provider) == "" {
		return "ollama_cloud"
	}
	return strings.TrimSpace(provider)
}

func isLocalOllamaBaseURL(baseURL string) bool {
	u, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil {
		return true
	}

	host := strings.ToLower(strings.TrimSpace(u.Hostname()))
	if host == "" {
		return true
	}

	if host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "0.0.0.0" || host == "host.docker.internal" {
		return true
	}

	ip := net.ParseIP(host)
	if ip != nil && ip.IsLoopback() {
		return true
	}

	return false
}
