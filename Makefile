backend-dev:
	uvicorn backend.api.main:app --reload --port 10003

backend-dev-server:
	uvicorn backend.api.main:app --reload --port 10003 --host 116.202.210.102