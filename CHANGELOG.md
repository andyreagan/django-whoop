# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-11-04

### Added
- Complete dashboard view with summary statistics and recent data visualization
- Data viewing pages for recovery, sleep, strain, and workouts
- Data syncing views for recent (7 days) and historical data
- Management command `sync_whoop` for CLI-based data synchronization
- Comprehensive Django admin interface for all models
- Error handling and user feedback throughout the application
- New templates:
  - Dashboard with stats and data tables
  - Data views for all WHOOP metrics
  - Sync success/error feedback pages
  - Enhanced login/reauth forms with error display
- Complete URL routing for all features
- Comprehensive README documentation with usage examples

### Changed
- Implemented complete token refresh logic with timestamp-based and API validation
- Fixed template inheritance issues (all templates now properly extend base)
- Enhanced error handling in authentication views
- Improved user experience with better navigation and feedback

### Fixed
- Token refresh logic now properly checks expiration
- Template inheritance corrected for all WHOOP templates
- Authentication error handling improved

## [0.1] - 2021-03-18

### Added
- Initial release with basic WHOOP integration
- Models for Daily, Recovery, Sleep, Strain, Workout, HR, and JournalEntry data
- Basic authentication with WHOOP API
- API pull functions for data retrieval
- Basic admin registration
- Bulk loading script
