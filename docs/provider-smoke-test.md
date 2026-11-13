# Provider smoke test

These checks are intentionally credentialed and must be run only against
cameras the operator owns or is authorized to monitor.

## Direct RTSP/WHEP bridge

Create a camera with a provider-neutral URL and bridge configuration:

```json
{
  "name": "living room bridge",
  "stream_url": "arlo://living-room",
  "protocol": "arlo",
  "provider_config": {
    "rtsp_url": "rtsp://127.0.0.1:8554/arlo-living-room"
  }
}
```

Confirm that the ingestion logs show decoded frames, vision publishes
detections, and an event appears with a clip key. The API response must expose
only a signed clip URL.

## Cloud WHEP provider

Set the provider token through the environment or a secret file, configure
`provider_config.whep_url` (or the provider’s `*_WHEP_URL_TEMPLATE`), and use a
`ring://`, `arlo://`, or `wyze://` device URL. Confirm an SDP offer/answer is
completed and frames arrive for at least five minutes.

Credential-bearing HTTPS control endpoints must use one of the built-in vendor
hosts or a host listed in the operator-only `PROVIDER_ALLOWED_CONTROL_HOSTS`
environment variable (comma-separated). Arbitrary camera-configured hosts are
rejected before a token-bearing request is made. Local bridges may use
loopback HTTP.

## Nest

Set `NEST_ACCESS_TOKEN`, `NEST_PROJECT_ID`, and a `nest://device-id` URL. Confirm
the Device Access `GenerateWebRtcStream` command returns an answer SDP and that
the audio/data transceivers do not prevent video frames from arriving.

Record provider, camera identifier, start/end time, frame count, event count,
and any reconnects. Never put access tokens in this record.
