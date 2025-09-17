"""Auto-generated TypedDict definitions from OpenAPI spec."""
from __future__ import annotations

from typing import Dict, List, Literal, NotRequired, TypedDict, Union
from datetime import datetime, date


AccessToken = str

RefreshToken = str

class JWTData(TypedDict):
    authMode: NotRequired[str]
    credentialKey: NotRequired[str]
    hasT3plus: NotRequired[bool]
    t3plusSubscriptionTier: NotRequired[Literal["manual", "basic", "team", "enterprise", "corporate"]]
    username: NotRequired[str]
    hostname: NotRequired[str]


class SearchResponse(TypedDict):
    data: NotRequired[List[Dict[str, Any]]]
    queriedMetrcEndpointIds: NotRequired[List[EndpointId]]
    failedMetrcEndpointIds: NotRequired[List[EndpointId]]


EndpointId = Literal["ACTIVE_HARVESTS", "ONHOLD_HARVESTS", "INACTIVE_HARVESTS", "ACTIVE_ITEMS", "DISCONTINUE_ITEMS", "ACTIVE_STRAINS", "DISCONTINUE_STRAINS", "CREATE_STRAINS", "ACTIVE_PACKAGES", "ONHOLD_PACKAGES", "INACTIVE_PACKAGES", "INTRANSIT_PACKAGES", "TRANSFERRED_PACKAGES", "PACKAGE_HISTORY", "PACKAGE_LABRESULTS", "PACKAGE_SOURCE_HARVESTS", "CREATE_PACKAGES_SOURCE_PACKAGES", "CREATE_PACKAGES_SOURCE_ITEMS", "ACTIVE_PLANTBATCHES", "ONHOLD_PLANTBATCHES", "INACTIVE_PLANTBATCHES", "VEGETATIVE_PLANTS", "FLOWERING_PLANTS", "ONHOLD_PLANTS", "INACTIVE_PLANTS", "INCOMING_ACTIVE_TRANSFERS", "INCOMING_INACTIVE_TRANSFERS", "OUTGOING_ACTIVE_TRANSFERS", "OUTGOING_INACTIVE_TRANSFERS", "OUTGOING_REJECTED_TRANSFERS", "TRANSFER_DELIVERIES", "TRANSFER_TRANSPORTER_DETAILS", "DELIVERY_TRANSPORTERS", "TRANSFER_PACKAGES", "TRANSFER_HISTORY", "CREATE_TRANSFER_DESTINATIONS", "CREATE_DELIVERY_TRANSPORTERS", "PACKAGE_LABRESULTS_DOCUMENT", "CREATE_PACKAGES_FROM_PACKAGES", "CREATE_PACKAGES_INPUTS", "CREATE_TRANSFER", "TRANSFER_MANIFEST", "CREATE_TRANSFER_INPUTS", "ADD_PACKAGE_NOTES"]

SecretKey = str

MetrcCredentialAuthPayload = Any

class MetrcSessionAuthPayload(TypedDict):
    username: str
    hostname: MetrcHostname
    cookies: Dict[str, Any]
    facilities: List[Dict[str, Any]]
    apiVerificationToken: str


class Pagination(TypedDict):
    page: NotRequired[int]
    totalPages: NotRequired[int]
    pageSize: NotRequired[int]
    total: NotRequired[int]


class T3GenerateLabelsPayload(TypedDict):
    labelTemplateLayoutConfig: T3LabelTemplateLayoutConfig
    labelContentLayoutConfig: T3LabelContentLayoutConfig
    labelContentDataList: List[Dict[str, Any]]
    commonContentData: NotRequired[Dict[str, Any]]
    images: NotRequired[Dict[str, Any]]
    renderingOptions: NotRequired[T3LabelRenderingOptions]
    disposition: NotRequired[Literal["inline", "attachment"]]


class T3GenerateLabelsPayload_DEPRECATED(TypedDict):
    labelTemplateLayoutId: str
    labelContentLayoutId: str
    labelContentData: List[Dict[str, Any]]
    renderingOptions: NotRequired[Dict[str, Any]]
    debug: NotRequired[bool]
    forcePromo: NotRequired[bool]
    disposition: NotRequired[Literal["inline", "attachment"]]


T3LabelContentLayoutsResponse = Any

T3LabelTemplateLayoutsResponse = Any

class T3IncomingTransferManifest(TypedDict):
    transfer.dataModel: NotRequired[str]
    transfer.retrievedAt: NotRequired[datetime]
    transfer.licenseNumber: NotRequired[str]
    transfer.index: NotRequired[Literal["ACTIVE_INCOMING_TRANSFER", "INACTIVE_INCOMING_TRANSFER"]]
    transfer.id: NotRequired[int]
    transfer.manifestNumber: NotRequired[str]
    transfer.shipmentLicenseTypeName: NotRequired[str]
    transfer.shipperFacilityLicenseNumber: NotRequired[str]
    transfer.shipperFacilityName: NotRequired[str]
    transfer.name: NotRequired[str]
    transfer.transporterFacilityLicenseNumber: NotRequired[str]
    transfer.transporterFacilityName: NotRequired[str]
    transfer.driverName: NotRequired[str]
    transfer.driverOccupationalLicenseNumber: NotRequired[str]
    transfer.driverVehicleLicenseNumber: NotRequired[str]
    transfer.vehicleMake: NotRequired[str]
    transfer.vehicleModel: NotRequired[str]
    transfer.vehicleLicensePlateNumber: NotRequired[str]
    transfer.deliveryFacilities: NotRequired[str]
    transfer.deliveryCount: NotRequired[int]
    transfer.receivedDeliveryCount: NotRequired[int]
    transfer.packageCount: NotRequired[int]
    transfer.receivedPackageCount: NotRequired[int]
    transfer.containsPlantPackage: NotRequired[bool]
    transfer.containsProductPackage: NotRequired[bool]
    transfer.containsTradeSample: NotRequired[bool]
    transfer.containsDonation: NotRequired[bool]
    transfer.containsTestingSample: NotRequired[bool]
    transfer.containsProductRequiresRemediation: NotRequired[bool]
    transfer.containsRemediatedProductPackage: NotRequired[bool]
    transfer.editCount: NotRequired[int]
    transfer.canEdit: NotRequired[bool]
    transfer.canEditOutgoingInactive: NotRequired[bool]
    transfer.isVoided: NotRequired[bool]
    transfer.createdDateTime: NotRequired[datetime]
    transfer.createdByUserName: NotRequired[str]
    transfer.lastModified: NotRequired[datetime]
    transfer.deliveryId: NotRequired[int]
    transfer.recipientFacilityId: NotRequired[int]
    transfer.recipientFacilityLicenseNumber: NotRequired[str]
    transfer.recipientFacilityName: NotRequired[str]
    transfer.shipmentTypeName: NotRequired[str]
    transfer.shipmentTransactionTypeName: NotRequired[str]
    transfer.estimatedDepartureDateTime: NotRequired[datetime]
    transfer.actualDepartureDateTime: NotRequired[datetime]
    transfer.estimatedArrivalDateTime: NotRequired[datetime]
    transfer.actualArrivalDateTime: NotRequired[datetime]
    transfer.deliveryPackageCount: NotRequired[int]
    transfer.deliveryReceivedPackageCount: NotRequired[int]
    transfer.receivedByName: NotRequired[str]
    transfer.receivedDateTime: NotRequired[datetime]
    transfer.estimatedReturnDepartureDateTime: NotRequired[datetime]
    transfer.actualReturnDepartureDateTime: NotRequired[datetime]
    transfer.estimatedReturnArrivalDateTime: NotRequired[datetime]
    transfer.actualReturnArrivalDateTime: NotRequired[datetime]
    transfer.rejectedPackagesReturned: NotRequired[bool]
    transfer.transporterAllApprovalDate: NotRequired[datetime]
    transfer.destinationsAllApprovalDate: NotRequired[datetime]
    transfer.transportersAutomaticallyApproved: NotRequired[bool]
    transfer.destinationsAutomaticallyApproved: NotRequired[bool]
    transfer.approvalRejectDateTime: NotRequired[datetime]
    transfer.approvalRejectedByUser: NotRequired[str]
    transfer.approvalRejectedFacilityLicenseNumber: NotRequired[str]
    transfer.approvalRejectReasonId: NotRequired[str]
    transfer.tollingAgreementFileSystemId: NotRequired[float]
    transfer.invoiceNumber: NotRequired[str]
    transporter.dataModel: NotRequired[str]
    transporter.retrievedAt: NotRequired[datetime]
    transporter.licenseNumber: NotRequired[str]
    transporter.transporterFacilityLicenseNumber: NotRequired[str]
    transporter.transporterFacilityName: NotRequired[str]
    transporter.transporterDirectionName: NotRequired[Literal["Outbound"]]
    transporter.transporterApprovalDate: NotRequired[datetime]
    transporter.transporterAutoApproval: NotRequired[bool]
    transporter.driverName: NotRequired[str]
    transporter.driverOccupationalLicenseNumber: NotRequired[str]
    transporter.driverVehicleLicenseNumber: NotRequired[str]
    transporter.driverLayoverLeg: NotRequired[str]
    transporter.vehicleMake: NotRequired[str]
    transporter.vehicleModel: NotRequired[str]
    transporter.vehicleLicensePlateNumber: NotRequired[str]
    transporter.acceptedDateTime: NotRequired[datetime]
    transporter.isLayover: NotRequired[bool]
    transporter.estimatedDepartureDateTime: NotRequired[datetime]
    transporter.actualDepartureDateTime: NotRequired[datetime]
    transporter.estimatedArrivalDateTime: NotRequired[datetime]
    transporter.actualArrivalDateTime: NotRequired[datetime]
    package.id: int
    package.dataModel: NotRequired[str]
    package.retrievedAt: NotRequired[datetime]
    package.licenseNumber: NotRequired[str]
    package.index: NotRequired[Literal["TRANSFERRED_PACKAGE"]]
    package.packageId: int
    package.recipientFacilityLicenseNumber: str
    package.recipientFacilityName: str
    package.manifestNumber: str
    package.packageLabel: str
    package.sourceHarvestNames: NotRequired[str]
    package.sourcePackageLabels: NotRequired[str]
    package.productName: str
    package.productCategoryName: str
    package.itemStrainName: str
    package.labTestingStateName: LabTestingStates
    package.shippedQuantity: float
    package.shippedUnitOfMeasureAbbreviation: str
    package.grossWeight: float
    package.grossUnitOfWeightAbbreviation: str
    package.shipperWholesalePrice: NotRequired[float]
    package.receivedQuantity: float
    package.receivedUnitOfMeasureAbbreviation: str
    package.receiverWholesalePrice: NotRequired[float]
    package.shipmentPackageStateName: Literal["Accepted", "Rejected", "Pending"]
    package.actualDepartureDateTime: NotRequired[datetime]
    package.receivedDateTime: datetime
    package.processingJobTypeName: NotRequired[str]


class T3OutgoingTransferManifest(TypedDict):
    transfer.dataModel: NotRequired[str]
    transfer.retrievedAt: NotRequired[datetime]
    transfer.licenseNumber: NotRequired[str]
    transfer.index: NotRequired[Literal["ACTIVE_OUTGOING_TRANSFER", "INACTIVE_OUTGOING_TRANSFER", "REJECTED_TRANSFER"]]
    transfer.id: NotRequired[int]
    transfer.manifestNumber: NotRequired[str]
    transfer.shipmentLicenseTypeName: NotRequired[str]
    transfer.shipperFacilityLicenseNumber: NotRequired[str]
    transfer.shipperFacilityName: NotRequired[str]
    transfer.name: NotRequired[str]
    transfer.transporterFacilityLicenseNumber: NotRequired[str]
    transfer.transporterFacilityName: NotRequired[str]
    transfer.driverName: NotRequired[str]
    transfer.driverOccupationalLicenseNumber: NotRequired[str]
    transfer.driverVehicleLicenseNumber: NotRequired[str]
    transfer.vehicleMake: NotRequired[str]
    transfer.vehicleModel: NotRequired[str]
    transfer.vehicleLicensePlateNumber: NotRequired[str]
    transfer.deliveryFacilities: NotRequired[str]
    transfer.deliveryCount: NotRequired[int]
    transfer.receivedDeliveryCount: NotRequired[int]
    transfer.packageCount: NotRequired[int]
    transfer.receivedPackageCount: NotRequired[int]
    transfer.containsPlantPackage: NotRequired[bool]
    transfer.containsProductPackage: NotRequired[bool]
    transfer.containsTradeSample: NotRequired[bool]
    transfer.containsDonation: NotRequired[bool]
    transfer.containsTestingSample: NotRequired[bool]
    transfer.containsProductRequiresRemediation: NotRequired[bool]
    transfer.containsRemediatedProductPackage: NotRequired[bool]
    transfer.editCount: NotRequired[int]
    transfer.canEdit: NotRequired[bool]
    transfer.canEditOutgoingInactive: NotRequired[bool]
    transfer.isVoided: NotRequired[bool]
    transfer.createdDateTime: NotRequired[datetime]
    transfer.createdByUserName: NotRequired[str]
    transfer.lastModified: NotRequired[datetime]
    transfer.deliveryId: NotRequired[int]
    transfer.recipientFacilityId: NotRequired[int]
    transfer.recipientFacilityLicenseNumber: NotRequired[str]
    transfer.recipientFacilityName: NotRequired[str]
    transfer.shipmentTypeName: NotRequired[str]
    transfer.shipmentTransactionTypeName: NotRequired[str]
    transfer.estimatedDepartureDateTime: NotRequired[datetime]
    transfer.actualDepartureDateTime: NotRequired[datetime]
    transfer.estimatedArrivalDateTime: NotRequired[datetime]
    transfer.actualArrivalDateTime: NotRequired[datetime]
    transfer.deliveryPackageCount: NotRequired[int]
    transfer.deliveryReceivedPackageCount: NotRequired[int]
    transfer.receivedByName: NotRequired[str]
    transfer.receivedDateTime: NotRequired[datetime]
    transfer.estimatedReturnDepartureDateTime: NotRequired[datetime]
    transfer.actualReturnDepartureDateTime: NotRequired[datetime]
    transfer.estimatedReturnArrivalDateTime: NotRequired[datetime]
    transfer.actualReturnArrivalDateTime: NotRequired[datetime]
    transfer.rejectedPackagesReturned: NotRequired[bool]
    transfer.transporterAllApprovalDate: NotRequired[datetime]
    transfer.destinationsAllApprovalDate: NotRequired[datetime]
    transfer.transportersAutomaticallyApproved: NotRequired[bool]
    transfer.destinationsAutomaticallyApproved: NotRequired[bool]
    transfer.approvalRejectDateTime: NotRequired[datetime]
    transfer.approvalRejectedByUser: NotRequired[str]
    transfer.approvalRejectedFacilityLicenseNumber: NotRequired[str]
    transfer.approvalRejectReasonId: NotRequired[str]
    transfer.tollingAgreementFileSystemId: NotRequired[float]
    transfer.invoiceNumber: NotRequired[str]
    transporter.dataModel: NotRequired[str]
    transporter.retrievedAt: NotRequired[datetime]
    transporter.licenseNumber: NotRequired[str]
    transporter.transporterFacilityLicenseNumber: NotRequired[str]
    transporter.transporterFacilityName: NotRequired[str]
    transporter.transporterDirectionName: NotRequired[Literal["Outbound"]]
    transporter.transporterApprovalDate: NotRequired[datetime]
    transporter.transporterAutoApproval: NotRequired[bool]
    transporter.driverName: NotRequired[str]
    transporter.driverOccupationalLicenseNumber: NotRequired[str]
    transporter.driverVehicleLicenseNumber: NotRequired[str]
    transporter.driverLayoverLeg: NotRequired[str]
    transporter.vehicleMake: NotRequired[str]
    transporter.vehicleModel: NotRequired[str]
    transporter.vehicleLicensePlateNumber: NotRequired[str]
    transporter.acceptedDateTime: NotRequired[datetime]
    transporter.isLayover: NotRequired[bool]
    transporter.estimatedDepartureDateTime: NotRequired[datetime]
    transporter.actualDepartureDateTime: NotRequired[datetime]
    transporter.estimatedArrivalDateTime: NotRequired[datetime]
    transporter.actualArrivalDateTime: NotRequired[datetime]
    transporterDetails.dataModel: NotRequired[str]
    transporterDetails.retrievedAt: NotRequired[datetime]
    transporterDetails.licenseNumber: NotRequired[str]
    transporterDetails.shipmentPlanId: NotRequired[int]
    transporterDetails.shipmentDeliveryId: NotRequired[int]
    transporterDetails.transporterDirection: NotRequired[Literal["Outbound"]]
    transporterDetails.transporterFacilityId: NotRequired[int]
    transporterDetails.lineNumber: NotRequired[int]
    transporterDetails.driverName: NotRequired[str]
    transporterDetails.driverOccupationalLicenseNumber: NotRequired[str]
    transporterDetails.driverVehicleLicenseNumber: NotRequired[str]
    transporterDetails.driverLayoverLeg: NotRequired[str]
    transporterDetails.vehicleMake: NotRequired[str]
    transporterDetails.vehicleModel: NotRequired[str]
    transporterDetails.vehicleLicensePlateNumber: NotRequired[str]
    transporterDetails.actualDriverStartDateTime: NotRequired[datetime]
    transporterDetails.isVoided: NotRequired[bool]
    transporterDetails.receivedDateTime: NotRequired[datetime]
    transporterDetails.receivedDeliveryCount: NotRequired[int]
    delivery.id: NotRequired[float]
    delivery.dataModel: NotRequired[str]
    delivery.retrievedAt: NotRequired[datetime]
    delivery.licenseNumber: NotRequired[str]
    delivery.actualArrivalDateTime: NotRequired[datetime]
    delivery.actualDepartureDateTime: NotRequired[datetime]
    delivery.actualReturnArrivalDateTime: NotRequired[datetime]
    delivery.actualReturnDepartureDateTime: NotRequired[datetime]
    delivery.deliveryPackageCount: NotRequired[int]
    delivery.deliveryReceivedPackageCount: NotRequired[int]
    delivery.estimatedArrivalDateTime: NotRequired[datetime]
    delivery.estimatedDepartureDateTime: NotRequired[datetime]
    delivery.estimatedReturnArrivalDateTime: NotRequired[datetime]
    delivery.estimatedReturnDepartureDateTime: NotRequired[datetime]
    delivery.grossUnitOfWeightAbbreviation: NotRequired[str]
    delivery.grossUnitOfWeightId: NotRequired[int]
    delivery.grossWeight: NotRequired[float]
    delivery.plannedRoute: NotRequired[str]
    delivery.receivedByName: NotRequired[str]
    delivery.receivedDateTime: NotRequired[datetime]
    delivery.recipientFacilityId: NotRequired[int]
    delivery.recipientFacilityLicenseNumber: NotRequired[str]
    delivery.recipientFacilityName: NotRequired[str]
    delivery.rejectedPackagesReturned: NotRequired[bool]
    delivery.shipmentTransactionTypeName: NotRequired[str]
    delivery.shipmentTypeName: NotRequired[Literal["Transfer"]]
    delivery.recipientApprovalDate: NotRequired[datetime]
    delivery.recipientAutoApproval: NotRequired[bool]
    delivery.tollingAgreementFileSystemId: NotRequired[float]
    delivery.invoiceNumber: NotRequired[str]
    package.id: int
    package.dataModel: NotRequired[str]
    package.retrievedAt: NotRequired[datetime]
    package.licenseNumber: NotRequired[str]
    package.index: NotRequired[Literal["TRANSFERRED_PACKAGE"]]
    package.packageId: int
    package.recipientFacilityLicenseNumber: str
    package.recipientFacilityName: str
    package.manifestNumber: str
    package.packageLabel: str
    package.sourceHarvestNames: NotRequired[str]
    package.sourcePackageLabels: NotRequired[str]
    package.productName: str
    package.productCategoryName: str
    package.itemStrainName: str
    package.labTestingStateName: LabTestingStates
    package.shippedQuantity: float
    package.shippedUnitOfMeasureAbbreviation: str
    package.grossWeight: float
    package.grossUnitOfWeightAbbreviation: str
    package.shipperWholesalePrice: NotRequired[float]
    package.receivedQuantity: float
    package.receivedUnitOfMeasureAbbreviation: str
    package.receiverWholesalePrice: NotRequired[float]
    package.shipmentPackageStateName: Literal["Accepted", "Rejected", "Pending"]
    package.actualDepartureDateTime: NotRequired[datetime]
    package.receivedDateTime: datetime
    package.processingJobTypeName: NotRequired[str]


class T3LabelContentData(TypedDict):
    text1: NotRequired[str]
    text2: NotRequired[str]
    text3: NotRequired[str]
    text4: NotRequired[str]
    text5: NotRequired[str]
    text6: NotRequired[str]
    text7: NotRequired[str]
    text8: NotRequired[str]


T3LabelContentDataListResponse = Any

T3LabelContentLayoutElementType = Literal["TEXT", "CODE128_BARCODE", "CODE39_BARCODE", "QR_CODE", "IMAGE", "BOX", "TABLE"]

T3LabelContentLayoutElementTextResizeStrategy = Literal["ALLOW_OVERFLOW", "TRUNCATE_TEXT", "SHRINK_TEXT"]

T3LabelContentLayoutElementParagraphFontName = Literal["Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique", "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique", "Symbol", "ZapfDingbats"]

class T3LabelContentLayoutConfig(TypedDict):
    """Data describing how each label will be laid out, including a list of pieces and how they are arranged."""
    name: NotRequired[str]
    minAspectRatio: NotRequired[float]
    maxAspectRatio: NotRequired[float]
    labelContentLayoutElements: List[T3LabelContentLayoutElement]


class T3LabelTemplateLayoutConfig(TypedDict):
    """Describes the label layout on a printed medium.
Capable of supporting any rectangular printable medium, with an arbitrarily sized grid of labels.
Assumes that multiple labels are arranged in a centered grid, and arranged with even spacing.
NOTE: y-coordinates are inverted."""
    name: NotRequired[str]
    pagesizeXIn: NotRequired[float]
    pagesizeYIn: NotRequired[float]
    labelWidthIn: NotRequired[float]
    labelHeightIn: NotRequired[float]
    xGapIn: NotRequired[float]
    yGapIn: NotRequired[float]
    numColumns: NotRequired[int]
    numRows: NotRequired[int]
    pageMarginTopIn: NotRequired[float]
    pageMarginLeftIn: NotRequired[float]
    labelPaddingXIn: NotRequired[float]
    labelPaddingYIn: NotRequired[float]


class T3LabelRenderingOptions(TypedDict):
    """Options for controlling how 1D barcodes will render."""
    debug: NotRequired[bool]
    enableWatermark: NotRequired[bool]
    reversePrintOrder: NotRequired[bool]
    rotationDegrees: NotRequired[float]
    labelCopies: NotRequired[int]
    barcodeBarThickness: NotRequired[float]
    labelMarginThickness: NotRequired[float]
    renderingVersion: NotRequired[float]


class T3LabelContentLayoutElement(TypedDict):
    """Describes the bounding rectangle and styling of one piece of a label layout."""
    name: NotRequired[str]
    elementType: T3LabelContentLayoutElementType
    xStartFraction: NotRequired[float]
    xEndFraction: NotRequired[float]
    yStartFraction: NotRequired[float]
    yEndFraction: NotRequired[float]
    valueTemplate: NotRequired[str]
    paragraphFontName: NotRequired[T3LabelContentLayoutElementParagraphFontName]
    paragraphFontSize: NotRequired[float]
    horizontalParagraphAlignment: NotRequired[Literal["LEFT", "CENTER", "RIGHT"]]
    verticalParagraphAlignment: NotRequired[Literal["TOP", "CENTER", "BOTTOM"]]
    paragraphSpacing: NotRequired[float]
    enabled: NotRequired[bool]
    paragraphTextResizeStrategy: NotRequired[T3LabelContentLayoutElementTextResizeStrategy]


class T3PackageLabelsPayload(TypedDict):
    labelTemplateLayoutId: str
    labelContentLayoutId: str
    data: List[str]
    renderingOptions: NotRequired[Dict[str, Any]]
    debug: NotRequired[bool]


class T3PackageLabelsPayload_DEPRECATED(TypedDict):
    labelTemplateLayoutId: str
    labelContentLayoutId: str
    data: List[str]
    renderingOptions: NotRequired[Dict[str, Any]]
    debug: NotRequired[bool]


class ExtractedLabResult(TypedDict):
    labTestResultId: NotRequired[float]
    labTestDetailId: NotRequired[float]
    labResultTestName: NotRequired[str]
    labResultTestValue: NotRequired[float]
    labResultTestUnit: NotRequired[str]
    labResultBatchName: NotRequired[str]
    fullLabResultTestName: NotRequired[str]
    passed: NotRequired[bool]
    tags: NotRequired[List[str]]


MetrcHostname = str

class UnitOfMeasure(TypedDict):
    abbreviation: NotRequired[str]
    fromBaseFactor: NotRequired[float]
    id: NotRequired[int]
    isArchived: NotRequired[bool]
    isBaseUnit: NotRequired[bool]
    name: NotRequired[str]
    quantityType: NotRequired[str]
    toBaseFactor: NotRequired[float]


LabTestingStates = Literal["NotSubmitted", "SubmittedForTesting", "TestFailed", "TestPassed", "TestingInProgress", "AwaitingConfirmation", "RetestFailed", "RetestPassed", "Remediated", "SelectedForRandomTesting", "NotRequired", "ProcessValidated"]

class MetrcLocation(TypedDict):
    forHarvests: NotRequired[bool]
    forPackages: NotRequired[bool]
    forPlantBatches: NotRequired[bool]
    forPlants: NotRequired[bool]
    id: NotRequired[int]
    isArchived: NotRequired[bool]
    locationTypeId: NotRequired[int]
    locationTypeName: NotRequired[str]
    name: NotRequired[str]


MetrcLocationListResponse = Dict[str, Any]

MetrcRemediationMethod = Any

MetrcLicense = Any

MetrcState = Any

class MetrcTag(TypedDict):
    id: NotRequired[int]
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    index: NotRequired[Literal["AVAILABLE_TAG", "USED_TAG", "VOID_TAG"]]
    commissionedDateTime: NotRequired[datetime]
    detachedDateTime: NotRequired[datetime]
    facilityId: NotRequired[int]
    groupTagTypeId: NotRequired[str]
    groupTagTypeName: NotRequired[str]
    isArchived: NotRequired[bool]
    isUsed: NotRequired[bool]
    label: NotRequired[str]
    lastModified: NotRequired[datetime]
    maxGroupSize: NotRequired[int]
    statusName: NotRequired[str]
    tagInventoryTypeName: NotRequired[str]
    tagTypeId: NotRequired[str]
    tagTypeName: NotRequired[str]
    usedDateTime: NotRequired[datetime]


MetrcTagListResponse = Dict[str, Any]

MetrcStrain = Any

MetrcStrainListResponse = Dict[str, Any]

MetrcItem = Any

MetrcItemListResponse = Dict[str, Any]

UnitOfMeasureAbbreviation = Literal["g", "mg", "kg", "oz", "lb", "ml", "l", "ea"]

MetrcPackage = Any

MetrcSuperpackage = Any

MetrcSuperpackageListResponse = Dict[str, Any]

MetrcPackageListResponse = Dict[str, Any]

MetrcDeliveryPackage = Any

MetrcDeliveryPackageListResponse = Dict[str, Any]

class MetrcTransferredPackage(TypedDict):
    id: int
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    index: NotRequired[Literal["TRANSFERRED_PACKAGE"]]
    packageId: int
    recipientFacilityLicenseNumber: str
    recipientFacilityName: str
    manifestNumber: str
    packageLabel: str
    sourceHarvestNames: NotRequired[str]
    sourcePackageLabels: NotRequired[str]
    productName: str
    productCategoryName: str
    itemStrainName: str
    labTestingStateName: LabTestingStates
    shippedQuantity: float
    shippedUnitOfMeasureAbbreviation: str
    grossWeight: float
    grossUnitOfWeightAbbreviation: str
    shipperWholesalePrice: NotRequired[float]
    receivedQuantity: float
    receivedUnitOfMeasureAbbreviation: str
    receiverWholesalePrice: NotRequired[float]
    shipmentPackageStateName: Literal["Accepted", "Rejected", "Pending"]
    actualDepartureDateTime: NotRequired[datetime]
    receivedDateTime: datetime
    processingJobTypeName: NotRequired[str]
    externalId: NotRequired[float]


MetrcTransferredPackageListResponse = Dict[str, Any]

MetrcHistory = Any

MetrcHistoryListResponse = Dict[str, Any]

class MetrcItemPhoto(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    fileName: NotRequired[str]
    productId: NotRequired[int]
    imageFileId: NotRequired[int]
    fileType: NotRequired[str]


MetrcItemPhotoListResponse = Dict[str, Any]

MetrcPackageLabResult = Any

MetrcPackageLabResultListResponse = Dict[str, Any]

MetrcPackageLabResultBatch = Any

MetrcPackageLabResultBatchListResponse = Dict[str, Any]

MetrcPackageRequiredLabtestBatch = Any

MetrcPackageRequiredLabtestBatchListResponse = Dict[str, Any]

MetrcPackageSourceHarvest = Any

MetrcPackageSourceHarvestListResponse = Dict[str, Any]

class MetrcIncomingTransfer(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    index: NotRequired[Literal["ACTIVE_INCOMING_TRANSFER", "INACTIVE_INCOMING_TRANSFER"]]
    id: NotRequired[int]
    manifestNumber: NotRequired[str]
    shipmentLicenseTypeName: NotRequired[str]
    shipperFacilityLicenseNumber: NotRequired[str]
    shipperFacilityName: NotRequired[str]
    name: NotRequired[str]
    transporterFacilityLicenseNumber: NotRequired[str]
    transporterFacilityName: NotRequired[str]
    driverName: NotRequired[str]
    driverOccupationalLicenseNumber: NotRequired[str]
    driverVehicleLicenseNumber: NotRequired[str]
    vehicleMake: NotRequired[str]
    vehicleModel: NotRequired[str]
    vehicleLicensePlateNumber: NotRequired[str]
    deliveryFacilities: NotRequired[str]
    deliveryCount: NotRequired[int]
    receivedDeliveryCount: NotRequired[int]
    packageCount: NotRequired[int]
    receivedPackageCount: NotRequired[int]
    containsPlantPackage: NotRequired[bool]
    containsProductPackage: NotRequired[bool]
    containsTradeSample: NotRequired[bool]
    containsDonation: NotRequired[bool]
    containsTestingSample: NotRequired[bool]
    containsProductRequiresRemediation: NotRequired[bool]
    containsRemediatedProductPackage: NotRequired[bool]
    editCount: NotRequired[int]
    canEdit: NotRequired[bool]
    canEditOutgoingInactive: NotRequired[bool]
    isVoided: NotRequired[bool]
    createdDateTime: NotRequired[datetime]
    createdByUserName: NotRequired[str]
    lastModified: NotRequired[datetime]
    deliveryId: NotRequired[int]
    recipientFacilityId: NotRequired[int]
    recipientFacilityLicenseNumber: NotRequired[str]
    recipientFacilityName: NotRequired[str]
    shipmentTypeName: NotRequired[str]
    shipmentTransactionTypeName: NotRequired[str]
    estimatedDepartureDateTime: NotRequired[datetime]
    actualDepartureDateTime: NotRequired[datetime]
    estimatedArrivalDateTime: NotRequired[datetime]
    actualArrivalDateTime: NotRequired[datetime]
    deliveryPackageCount: NotRequired[int]
    deliveryReceivedPackageCount: NotRequired[int]
    receivedByName: NotRequired[str]
    receivedDateTime: NotRequired[datetime]
    estimatedReturnDepartureDateTime: NotRequired[datetime]
    actualReturnDepartureDateTime: NotRequired[datetime]
    estimatedReturnArrivalDateTime: NotRequired[datetime]
    actualReturnArrivalDateTime: NotRequired[datetime]
    rejectedPackagesReturned: NotRequired[bool]
    transporterAllApprovalDate: NotRequired[datetime]
    destinationsAllApprovalDate: NotRequired[datetime]
    transportersAutomaticallyApproved: NotRequired[bool]
    destinationsAutomaticallyApproved: NotRequired[bool]
    approvalRejectDateTime: NotRequired[datetime]
    approvalRejectedByUser: NotRequired[str]
    approvalRejectedFacilityLicenseNumber: NotRequired[str]
    approvalRejectReasonId: NotRequired[str]
    PDFDocumentFileSystemId: NotRequired[float]
    invoiceNumber: NotRequired[str]
    lineNumber: NotRequired[int]


MetrcIncomingTransferListResponse = Dict[str, Any]

class MetrcOutgoingTransfer(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    index: NotRequired[Literal["ACTIVE_OUTGOING_TRANSFER", "INACTIVE_OUTGOING_TRANSFER", "REJECTED_TRANSFER"]]
    id: NotRequired[int]
    manifestNumber: NotRequired[str]
    shipmentLicenseTypeName: NotRequired[str]
    shipperFacilityLicenseNumber: NotRequired[str]
    shipperFacilityName: NotRequired[str]
    name: NotRequired[str]
    transporterFacilityLicenseNumber: NotRequired[str]
    transporterFacilityName: NotRequired[str]
    driverName: NotRequired[str]
    driverOccupationalLicenseNumber: NotRequired[str]
    driverVehicleLicenseNumber: NotRequired[str]
    vehicleMake: NotRequired[str]
    vehicleModel: NotRequired[str]
    vehicleLicensePlateNumber: NotRequired[str]
    deliveryFacilities: NotRequired[str]
    deliveryCount: NotRequired[int]
    receivedDeliveryCount: NotRequired[int]
    packageCount: NotRequired[int]
    receivedPackageCount: NotRequired[int]
    containsPlantPackage: NotRequired[bool]
    containsProductPackage: NotRequired[bool]
    containsTradeSample: NotRequired[bool]
    containsDonation: NotRequired[bool]
    containsTestingSample: NotRequired[bool]
    containsProductRequiresRemediation: NotRequired[bool]
    containsRemediatedProductPackage: NotRequired[bool]
    editCount: NotRequired[int]
    canEdit: NotRequired[bool]
    canEditOutgoingInactive: NotRequired[bool]
    isVoided: NotRequired[bool]
    createdDateTime: NotRequired[datetime]
    createdByUserName: NotRequired[str]
    lastModified: NotRequired[datetime]
    deliveryId: NotRequired[int]
    recipientFacilityId: NotRequired[int]
    recipientFacilityLicenseNumber: NotRequired[str]
    recipientFacilityName: NotRequired[str]
    shipmentTypeName: NotRequired[str]
    shipmentTransactionTypeName: NotRequired[str]
    estimatedDepartureDateTime: NotRequired[datetime]
    actualDepartureDateTime: NotRequired[datetime]
    estimatedArrivalDateTime: NotRequired[datetime]
    actualArrivalDateTime: NotRequired[datetime]
    deliveryPackageCount: NotRequired[int]
    deliveryReceivedPackageCount: NotRequired[int]
    receivedByName: NotRequired[str]
    receivedDateTime: NotRequired[datetime]
    estimatedReturnDepartureDateTime: NotRequired[datetime]
    actualReturnDepartureDateTime: NotRequired[datetime]
    estimatedReturnArrivalDateTime: NotRequired[datetime]
    actualReturnArrivalDateTime: NotRequired[datetime]
    rejectedPackagesReturned: NotRequired[bool]
    transporterAllApprovalDate: NotRequired[datetime]
    destinationsAllApprovalDate: NotRequired[datetime]
    transportersAutomaticallyApproved: NotRequired[bool]
    destinationsAutomaticallyApproved: NotRequired[bool]
    approvalRejectDateTime: NotRequired[datetime]
    approvalRejectedByUser: NotRequired[str]
    approvalRejectedFacilityLicenseNumber: NotRequired[str]
    approvalRejectReasonId: NotRequired[str]
    PDFDocumentFileSystemId: NotRequired[float]
    invoiceNumber: NotRequired[str]
    lineNumber: NotRequired[int]


MetrcOutgoingTransferListResponse = Dict[str, Any]

MetrcTransferTemplate = Dict[str, Any]

MetrcTransferTemplateListResponse = Dict[str, Any]

class MetrcTransferDelivery(TypedDict):
    id: NotRequired[float]
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    manifestNumber: NotRequired[int]
    deliveryNumber: NotRequired[int]
    actualArrivalDateTime: NotRequired[datetime]
    actualDepartureDateTime: NotRequired[datetime]
    actualReturnArrivalDateTime: NotRequired[datetime]
    actualReturnDepartureDateTime: NotRequired[datetime]
    deliveryPackageCount: NotRequired[int]
    deliveryReceivedPackageCount: NotRequired[int]
    estimatedArrivalDateTime: NotRequired[datetime]
    estimatedDepartureDateTime: NotRequired[datetime]
    estimatedReturnArrivalDateTime: NotRequired[datetime]
    estimatedReturnDepartureDateTime: NotRequired[datetime]
    grossUnitOfWeightAbbreviation: NotRequired[str]
    grossUnitOfWeightId: NotRequired[int]
    grossWeight: NotRequired[float]
    plannedRoute: NotRequired[str]
    receivedByName: NotRequired[str]
    receivedDateTime: NotRequired[datetime]
    recipientFacilityId: NotRequired[int]
    recipientFacilityLicenseNumber: NotRequired[str]
    recipientFacilityName: NotRequired[str]
    rejectedPackagesReturned: NotRequired[bool]
    shipmentTransactionTypeName: NotRequired[str]
    shipmentTypeName: NotRequired[Literal["Transfer"]]
    recipientApprovalDate: NotRequired[datetime]
    recipientAutoApproval: NotRequired[bool]
    PDFDocumentFileSystemId: NotRequired[float]
    invoiceNumber: NotRequired[str]


MetrcTransferDeliveryListResponse = Dict[str, Any]

class MetrcTransferTransporter(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    transporterFacilityLicenseNumber: NotRequired[str]
    transporterFacilityName: NotRequired[str]
    transporterDirectionName: NotRequired[Literal["Outbound"]]
    transporterApprovalDate: NotRequired[datetime]
    transporterAutoApproval: NotRequired[bool]
    driverName: NotRequired[str]
    driverOccupationalLicenseNumber: NotRequired[str]
    driverVehicleLicenseNumber: NotRequired[str]
    driverLayoverLeg: NotRequired[str]
    vehicleMake: NotRequired[str]
    vehicleModel: NotRequired[str]
    vehicleLicensePlateNumber: NotRequired[str]
    acceptedDateTime: NotRequired[datetime]
    isLayover: NotRequired[bool]
    estimatedDepartureDateTime: NotRequired[datetime]
    actualDepartureDateTime: NotRequired[datetime]
    estimatedArrivalDateTime: NotRequired[datetime]
    actualArrivalDateTime: NotRequired[datetime]


MetrcTransferTransporterListResponse = Dict[str, Any]

class MetrcTransferTransporterDetails(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    shipmentPlanId: NotRequired[int]
    shipmentDeliveryId: NotRequired[int]
    transporterDirection: NotRequired[Literal["Outbound"]]
    transporterFacilityId: NotRequired[int]
    lineNumber: NotRequired[int]
    driverName: NotRequired[str]
    driverOccupationalLicenseNumber: NotRequired[str]
    driverVehicleLicenseNumber: NotRequired[str]
    driverLayoverLeg: NotRequired[str]
    vehicleMake: NotRequired[str]
    vehicleModel: NotRequired[str]
    vehicleLicensePlateNumber: NotRequired[str]
    actualDriverStartDateTime: NotRequired[datetime]
    isVoided: NotRequired[bool]
    receivedDateTime: NotRequired[datetime]
    receivedDeliveryCount: NotRequired[int]


MetrcTransferTransporterDetailsListResponse = Dict[str, Any]

MetrcHarvest = Any

class MetrcHarvestPlant(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    harvestId: NotRequired[int]
    plantId: NotRequired[int]
    harvestCount: NotRequired[int]
    label: NotRequired[str]
    locationName: NotRequired[str]
    locationTypeName: NotRequired[Literal["Default Location Type", "Greenhouse", "Outdoor"]]
    patientLicenseNumber: NotRequired[str]
    plantBatchName: NotRequired[str]
    plantBatchTypeName: NotRequired[Literal["Clone", "Seed"]]
    harvestSpecificPlantCount: NotRequired[int]
    totalPlantCount: NotRequired[int]
    strainName: NotRequired[str]
    isOnHold: NotRequired[bool]
    plantedDate: NotRequired[date]
    vegetativeDate: NotRequired[date]
    floweringDate: NotRequired[date]
    destroyedDate: NotRequired[date]
    lastModified: NotRequired[datetime]


class MetrcHarvestPackage(TypedDict):
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    packageId: NotRequired[int]
    label: NotRequired[str]
    packageType: NotRequired[str]
    productName: NotRequired[str]
    productCategoryName: NotRequired[str]
    quantity: NotRequired[float]
    unitOfMeasureName: NotRequired[str]
    unitOfMeasureAbbreviation: NotRequired[str]
    isProductionBatch: NotRequired[bool]
    productionBatchNumber: NotRequired[str]
    actualDate: NotRequired[date]
    expirationDate: NotRequired[date]
    sellByDate: NotRequired[date]
    useByDate: NotRequired[date]
    isArchived: NotRequired[bool]
    isFinished: NotRequired[bool]


MetrcSalesReceipt = Any

MetrcSalesReceiptListResponse = Dict[str, Any]

MetrcTransaction = Any

MetrcTransactionListResponse = Dict[str, Any]

MetrcHarvestListResponse = Dict[str, Any]

MetrcHarvestPlantListResponse = Dict[str, Any]

MetrcHarvestPackageListResponse = Dict[str, Any]

class MetrcPlantBatch(TypedDict):
    id: NotRequired[int]
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    index: NotRequired[Literal["ACTIVE_PLANTBATCH", "ONHOLD_PLANTBATCH", "INACTIVE_PLANTBATCH"]]
    name: NotRequired[str]
    plantBatchTypeName: NotRequired[str]
    locationName: NotRequired[str]
    sublocationName: NotRequired[str]
    locationTypeName: NotRequired[str]
    strainId: NotRequired[int]
    strainName: NotRequired[str]
    patientLicenseNumber: NotRequired[str]
    untrackedCount: NotRequired[int]
    trackedCount: NotRequired[int]
    packagedCount: NotRequired[int]
    destroyedCount: NotRequired[int]
    sourcePackageLabel: NotRequired[str]
    sourcePlantLabel: NotRequired[str]
    sourcePlantBatchNames: NotRequired[str]
    multiPlantBatch: NotRequired[bool]
    plantedDate: NotRequired[date]
    lastModified: NotRequired[datetime]
    isOnHold: NotRequired[bool]


MetrcPlantBatchListResponse = Dict[str, Any]

class MetrcPlant(TypedDict):
    id: NotRequired[int]
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    licenseNumber: NotRequired[str]
    index: NotRequired[Literal["VEGETATIVE_PLANT", "FLOWERING_PLANT", "ONHOLD_PLANT", "INACTIVE_PLANT"]]
    label: NotRequired[str]
    stateName: NotRequired[Literal["Tracked", "Untracked", "Destroyed"]]
    growthPhaseName: NotRequired[Literal["Germination", "Vegetative", "Flowering", "Harvest"]]
    plantCount: NotRequired[int]
    groupTagTypeMax: NotRequired[int]
    tagTypeMax: NotRequired[int]
    plantBatchName: NotRequired[str]
    plantBatchTypeName: NotRequired[Literal["Clone", "Seed"]]
    strainId: NotRequired[int]
    strainName: NotRequired[str]
    locationName: NotRequired[str]
    sublocationName: NotRequired[str]
    locationTypeName: NotRequired[Literal["Default Location Type", "Greenhouse", "Outdoor"]]
    patientLicenseNumber: NotRequired[str]
    harvestCount: NotRequired[int]
    isOnHold: NotRequired[bool]
    plantedDate: NotRequired[date]
    vegetativeDate: NotRequired[date]
    floweringDate: NotRequired[date]
    destroyedDate: NotRequired[date]
    destroyedNote: NotRequired[str]
    destroyedByUserName: NotRequired[str]
    lastModified: NotRequired[datetime]
    survivedCount: NotRequired[int]
    motherPlantDate: NotRequired[date]
    descendedCount: NotRequired[int]
    clonedCount: NotRequired[int]


MetrcPlantListResponse = Dict[str, Any]

class MetrcCreateTransferInputsResponse(TypedDict):
    adding: NotRequired[bool]
    daysWholesalePriceCanEdit: NotRequired[int]
    defaultPhoneNumberForQuestions: NotRequired[str]
    destinationFacilities: NotRequired[List[Dict[str, Any]]]
    details: NotRequired[Dict[str, Any]]
    drivers: NotRequired[List[MetrcDriver]]
    editDeliveryDetailsOnly: NotRequired[bool]
    editWholesalePriceOnly: NotRequired[bool]
    facilities: NotRequired[Dict[str, Any]]
    isOutgoingInactive: NotRequired[bool]
    items: NotRequired[Dict[str, Any]]
    packages: NotRequired[List[Dict[str, Any]]]
    selectedDeliveryIds: NotRequired[List[int]]
    selectedTransferIds: NotRequired[List[int]]
    selectedTransferTemplateIds: NotRequired[Dict[str, Any]]
    transferTypes: NotRequired[List[Dict[str, Any]]]
    transporterFacilities: NotRequired[List[Dict[str, Any]]]
    unitsOfMeasure: NotRequired[List[UnitOfMeasure]]
    vehicles: NotRequired[List[MetrcVehicle]]


class MetrcCreatePackageInputsResponse(TypedDict):
    allowedProductionLabTestingStates: NotRequired[List[LabTestingStates]]
    allowedProductionProductCategoryIds: NotRequired[List[int]]
    details: NotRequired[str]
    harvestBatches: NotRequired[str]
    growthPhase: NotRequired[int]
    isProductDestruction: NotRequired[bool]
    itemCategoryIds: NotRequired[str]
    items: NotRequired[List[str]]
    labTestBatches: NotRequired[str]
    locations: NotRequired[List[MetrcLocation]]
    sublocations: NotRequired[List[str]]
    packages: NotRequired[List[str]]
    patientAffiliations: NotRequired[str]
    plantBatches: NotRequired[str]
    plants: NotRequired[str]
    remediationMethods: NotRequired[List[MetrcRemediationMethod]]
    submitForTesting: NotRequired[bool]
    tags: NotRequired[List[MetrcTag]]
    unitsOfMeasure: NotRequired[List[UnitOfMeasure]]


MetrcAddPackageNotePayload = List[Dict[str, Any]]

MetrcCreatePackagesFromPackagesPayload = List[Dict[str, Any]]

MetrcUnfinalizeSalesPayload = List[Dict[str, Any]]

MetrcUnfinishPackagesPayload = List[Dict[str, Any]]

class MetrcVoidSalesReceiptPayload(TypedDict):
    id: int


class MetrcDiscontinueItemPayload(TypedDict):
    id: int


class MetrcDiscontinueStrainPayload(TypedDict):
    id: int


MetrcCreateStrainsPayload = List[Dict[str, Any]]

class MetrcCreateTransferLikeData(TypedDict):
    """A schema representing a shipment with details about destinations, transporters, and packages."""
    destinations: List[Dict[str, Any]]


MetrcCreateTransfersPayload = List[MetrcCreateTransferLikeData]

MetrcUpdateTransfersPayload = List[Dict[str, Any]]

class MetrcVoidTransferPayload(TypedDict):
    id: int


MetrcCreateTransferTemplatesPayload = List[Dict[str, Any]]

MetrcUpdateTransferTemplatesPayload = List[Dict[str, Any]]

class MetrcArchiveTransferTemplatePayload(TypedDict):
    id: int


MetrcFacilityListResponse = Dict[str, Any]

class MetrcFacility(TypedDict):
    """A schema representing a facility with various details including license, address, and contact information."""
    licenseNumber: NotRequired[str]
    facilityName: NotRequired[str]
    id: NotRequired[int]
    hostname: NotRequired[str]
    dataModel: NotRequired[str]
    retrievedAt: NotRequired[datetime]
    index: NotRequired[Literal["TRANSPORTER", "DESTINATION"]]
    facilityTypeName: NotRequired[str]
    facilityType: NotRequired[str]
    physicalAddress: NotRequired[Dict[str, Any]]
    mainPhoneNumber: NotRequired[str]
    mobilePhoneNumber: NotRequired[str]


class MetrcDriver(TypedDict):
    driversLicenseNumber: NotRequired[str]
    employeeId: NotRequired[str]
    facilityId: NotRequired[int]
    id: NotRequired[int]
    isArchived: NotRequired[bool]
    lastModified: NotRequired[datetime]
    name: NotRequired[str]


class MetrcVehicle(TypedDict):
    facilityId: NotRequired[int]
    id: NotRequired[int]
    isArchived: NotRequired[bool]
    lastModified: NotRequired[datetime]
    licensePlateNumber: NotRequired[str]
    make: NotRequired[str]
    model: NotRequired[str]


MetrcTagReportResponse = Any

MetrcItemReportResponse = Any

MetrcPackageReportResponse = Any

MetrcPlantReportResponse = Any

MetrcPlantBatchReportResponse = Any

MetrcHarvestReportResponse = Any

MetrcSalesReceiptReportResponse = Any

IncomingTransferManifestReportResponse = Any

OutgoingTransferManifestReportResponse = Any
