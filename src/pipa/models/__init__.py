"""SQLAlchemy ORM models — import all models here so Alembic can discover them."""

from pipa.models.base import Base
from pipa.models.property import AddressHistory, Parcel, ParcelEvent, ParcelIdentifier, Property
from pipa.models.source import EvidenceItem, ScrapeRun, SourceHealth, SourceRecord, SourceRegistry
from pipa.models.freshness import DataFreshnessPolicy
from pipa.models.job import RefreshJob
from pipa.models.user import BuyerProfile, ScoringProfile, Tag, User, WatchlistEntry, property_tag
from pipa.models.analysis_models import AnalysisRun, AssumptionSet
from pipa.models.assessment import AssessmentSnapshot
from pipa.models.deed import DeedRecord
from pipa.models.listing import ListingEpisode, ListingSnapshot, PriceEvent, SaleEvent, StatusEvent
from pipa.models.listing_page import ListingPageSnapshot
from pipa.models.permit import PermitRecord, PlatRecord, ZoningRecord
from pipa.models.geometry import GeometrySnapshot, OverlayIntersection
from pipa.models.component import ComponentEvidence, ComponentSystem
from pipa.models.community import Community, CommunityAmenity, PropertyCommunityMembership
from pipa.models.hoa import HOADocument, HOAFeeHistory, HOAFinancialSnapshot, HOARule
from pipa.models.hazard import HazardProfile
from pipa.models.document import Document, ExtractedFact, PhotoAsset, PropertyNote
from pipa.models.alert import AlertEvent, AlertSubscription
from pipa.models.quote import InsuranceQuote, MortgageQuote, RepairEstimate
from pipa.models.nearby import NearbyRelationship
from pipa.models.decision import DecisionCase, DueDiligenceItem, RecommendationSnapshot
from pipa.models.development import DevelopmentCase, ZoningCase
from pipa.models.pipeline_run import PipelineRun, PipelineTaskRun
from pipa.models.app_setting import AppSetting

__all__ = [
    "Base",
    # property.py
    "Property", "Parcel", "ParcelIdentifier", "ParcelEvent", "AddressHistory",
    # source.py
    "SourceRegistry", "SourceRecord", "EvidenceItem", "SourceHealth", "ScrapeRun",
    # freshness.py
    "DataFreshnessPolicy",
    # job.py
    "RefreshJob",
    # user.py
    "User", "WatchlistEntry", "Tag", "BuyerProfile", "ScoringProfile", "property_tag",
    # analysis_models.py
    "AnalysisRun", "AssumptionSet",
    # assessment.py
    "AssessmentSnapshot",
    # deed.py
    "DeedRecord",
    # listing.py
    "ListingEpisode", "ListingSnapshot", "StatusEvent", "PriceEvent", "SaleEvent",
    # listing_page.py
    "ListingPageSnapshot",
    # permit.py
    "PermitRecord", "ZoningRecord", "PlatRecord",
    # geometry.py
    "GeometrySnapshot", "OverlayIntersection",
    # component.py
    "ComponentSystem", "ComponentEvidence",
    # community.py
    "Community", "PropertyCommunityMembership", "CommunityAmenity",
    # hoa.py
    "HOAFeeHistory", "HOARule", "HOAFinancialSnapshot", "HOADocument",
    # hazard.py
    "HazardProfile",
    # document.py
    "Document", "ExtractedFact", "PhotoAsset", "PropertyNote",
    # alert.py
    "AlertEvent", "AlertSubscription",
    # quote.py
    "MortgageQuote", "InsuranceQuote", "RepairEstimate",
    # nearby.py
    "NearbyRelationship",
    # decision.py
    "DecisionCase", "DueDiligenceItem", "RecommendationSnapshot",
    # development.py
    "DevelopmentCase", "ZoningCase",
    # pipeline_run.py
    "PipelineRun", "PipelineTaskRun",
    # app_setting.py
    "AppSetting",
]
