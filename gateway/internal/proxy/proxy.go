package proxy

import (
	"io"
	"net/http"
	"net/url"
	"time"
)

type ReverseProxy struct {
	client *http.Client
}

func NewReverseProxy() *ReverseProxy {
	return &ReverseProxy{
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

func (p *ReverseProxy) ForwardRequest(targetBaseURL string, path string, method string, body io.Reader, headers http.Header) (*http.Response, error) {
	targetURL, err := url.Parse(targetBaseURL + path)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest(method, targetURL.String(), body)
	if err != nil {
		return nil, err
	}

	if contentType := headers.Get("Content-Type"); contentType != "" {
		req.Header.Set("Content-Type", contentType)
	} else {
		req.Header.Set("Content-Type", "application/json")
	}

	return p.client.Do(req)
}

func CopyResponse(w http.ResponseWriter, resp *http.Response) {
	defer resp.Body.Close()

	for k, v := range resp.Header {
		for _, val := range v {
			w.Header().Add(k, val)
		}
	}

	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

func FallbackJsonResponse(w http.ResponseWriter, statusCode int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	if strData, ok := data.(string); ok {
		w.Write([]byte(strData))
		return
	}

	if bytesData, ok := data.([]byte); ok {
		w.Write(bytesData)
		return
	}
}
