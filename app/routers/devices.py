import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import raise_app_error
from app.models import Device
from app.schemas import DeviceCreateRequest, DeviceResponse
from app.security import require_api_key


router = APIRouter(
    prefix="/devices",
    tags=["devices"],
    dependencies=[Depends(require_api_key)],
)


def to_device_response(device: Device) -> DeviceResponse:
    return DeviceResponse(
        device_id=device.id,
        device_code=device.device_code,
        hardware_revision=device.hardware_revision,
        firmware_version=device.firmware_version,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    request: DeviceCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> DeviceResponse:
    device = db.scalar(select(Device).where(Device.device_code == request.device_code))
    if device is not None:
        response.status_code = status.HTTP_200_OK
        if request.hardware_revision is not None:
            device.hardware_revision = request.hardware_revision
        if request.firmware_version is not None:
            device.firmware_version = request.firmware_version
        db.commit()
        db.refresh(device)
        return to_device_response(device)

    device = Device(
        device_code=request.device_code,
        hardware_revision=request.hardware_revision,
        firmware_version=request.firmware_version,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return to_device_response(device)


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DeviceResponse:
    device = db.get(Device, device_id)
    if device is None:
        raise_app_error(
            status.HTTP_404_NOT_FOUND,
            "DEVICE_NOT_FOUND",
            "Device not found",
        )
    return to_device_response(device)
