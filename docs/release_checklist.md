# Release Checklist — rFactor2 Engineer

Date: _______________
Version: _____________

## Pre-Release

### Code Quality
- [ ] `go vet ./services/backend_go/...` passes with 0 warnings
- [ ] `go test ./services/backend_go/...` passes with all tests green
- [ ] `npx expo lint` (in apps/expo_app/) passes
- [ ] `npx jest` (in apps/expo_app/) passes
- [ ] No TODO/FIXME comments in critical paths

### Documentation
- [ ] API documentation updated (docs/openapi.yaml)
- [ ] README.md reflects current features
- [ ] AGENTS.md updated if architecture changed

## Build Phase

### Go Binary (Linux amd64)
- [ ] `$env:GOOS="linux"; $env:GOARCH="amd64"; go build -ldflags "-s -w" -o rf2engineer ./services/backend_go/cmd/server` completes
- [ ] Binary size is reasonable (< 50MB)
- [ ] Binary runs on target Linux server

### Expo Web Build
- [ ] `npx expo export -p web` completes (in apps/expo_app/)
- [ ] `dist/` copied to `services/backend_go/internal/web/dist/`
- [ ] Web app loads when served by Go binary

## QA Testing

### Smoke Tests
- [ ] Binary starts and serves on `:8080`
- [ ] `GET /api/health` returns `{"status":"healthy"}`
- [ ] Web app loads in browser at `http://localhost:8080`
- [ ] All navigation routes work

### Feature Validation
- [ ] Upload telemetry file (.csv or .mat) with progress
- [ ] Upload setup file (.svm)
- [ ] Select LLM model from dropdown
- [ ] Launch analysis → response within timeout
- [ ] Circuit map renders with GPS points
- [ ] Driving analysis text shows 5 points
- [ ] Setup table shows recommendations with % change
- [ ] Track library lists available tracks

### Error Handling
- [ ] Ollama offline shows descriptive error
- [ ] Invalid file type rejected
- [ ] Network error handled gracefully

## E2E Scenario

### Scenario 1: Full Analysis (target <5 min with llama3.2:latest)
```
Steps:
1. Open web app
2. Upload sample.csv + sample.svm
3. Select llama3.2:latest model
4. Launch analysis
5. Verify driving analysis text
6. Verify setup recommendations table
7. Verify circuit map
```
**Result**: **Pass/Fail** ___

## Deployment

### GCP Server (bitor@34.175.126.128)
- [ ] scp binary to server
- [ ] Stop old process
- [ ] Start new binary (systemd or screen)
- [ ] Verify Nginx proxy passes to :8080
- [ ] Verify https://telemetria.bot.nu loads
- [ ] Verify https://car-setup.com loads

## Sign-Off

**Tester**: _________________ Date: _______
**Release Ready**: **YES / NO**
