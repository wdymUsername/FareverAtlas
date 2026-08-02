"""Centralized Qt style sheets for the standalone minimap."""

MAP_WINDOW_STYLESHEET = r"""
QWidget#fareverTitleBar {
    background: #111820;
    border-bottom: 1px solid #2b3946;
}
QLabel#fareverTitleLabel {
    color: #aebbc6;
    background: transparent;
    border: none;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QMenuBar#fareverMenuBar {
    background: #111820;
    color: #b9c5cf;
    border: none;
    padding: 2px 5px;
    spacing: 3px;
}
QMenuBar#fareverMenuBar::item {
    background: transparent;
    border-radius: 3px;
    padding: 4px 9px;
}
QMenuBar#fareverMenuBar::item:selected {
    background: #263541;
    color: #eef3f7;
}
QMenuBar#fareverMenuBar::item:pressed {
    background: #314454;
}
QToolButton#mainMenuButton {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}
QToolButton#mainMenuButton:hover,
QToolButton#mainMenuButton:pressed {
    background: transparent;
    border: none;
}
QToolButton#mainMenuButton::menu-indicator {
    image: none;
    width: 0;
}
QFrame#mainNavigationOverlay {
    background: #313338;
    border: 1px solid #1e1f22;
    border-radius: 8px;
}
QWidget#mainNavigationSidebar {
    background: #2b2d31;
    border: none;
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
}
QWidget#mainNavigationPage,
QScrollArea#mainNavigationScroll,
QWidget#mainNavigationScrollBody {
    background: #313338;
    border: none;
}
QWidget#mainNavigationContent {
    background: #313338;
    border: none;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}
QScrollArea#mainNavigationScroll QScrollBar:vertical {
    width: 8px;
    margin: 0;
    background: #2b2d31;
    border-radius: 4px;
}
QScrollArea#mainNavigationScroll QScrollBar::handle:vertical {
    min-height: 30px;
    background: #1e1f22;
    border-radius: 4px;
}
QScrollArea#mainNavigationScroll QScrollBar::handle:vertical:hover {
    background: #111214;
}
QScrollArea#mainNavigationScroll QScrollBar::add-line:vertical,
QScrollArea#mainNavigationScroll QScrollBar::sub-line:vertical,
QScrollArea#mainNavigationScroll QScrollBar::add-page:vertical,
QScrollArea#mainNavigationScroll QScrollBar::sub-page:vertical {
    width: 0;
    height: 0;
    background: transparent;
}
QLabel#mainNavigationBrand {
    color: #f2f3f5;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 0 8px 12px 8px;
}
QLabel#mainNavigationSection {
    color: #949ba4;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 5px 8px 2px 8px;
}
QPushButton#mainNavigationEntry {
    min-height: 30px;
    max-height: 30px;
    padding: 0 9px;
    text-align: left;
    color: #b5bac1;
    background: transparent;
    border: none;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#mainNavigationEntry:hover {
    color: #dbdee1;
    background: #35373c;
}
QPushButton#mainNavigationEntry:checked {
    color: #f2f3f5;
    background: #404249;
}
QFrame#mainNavigationSeparator {
    background: #3f4147;
    border: none;
}
QLabel#mainNavigationVersion {
    color: #6d6f78;
    font-size: 9px;
    padding-left: 8px;
}
QLabel#mainNavigationHeading {
    color: #f2f3f5;
    font-size: 17px;
    font-weight: 700;
}
QLabel#mainNavigationHeaderNotice {
    color: #949ba4;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.4px;
}
QLabel#mainNavigationBody {
    color: #b5bac1;
    font-size: 11px;
}
QWidget#mainNavigationContent QGroupBox {
    color: #f2f3f5;
    background: #2b2d31;
    border: 1px solid #3f4147;
    border-radius: 5px;
    margin-top: 11px;
    padding-top: 7px;
    font-size: 10px;
    font-weight: 700;
}
QWidget#mainNavigationContent QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 9px;
    padding: 0 4px;
    color: #dbdee1;
    background: #2b2d31;
}
QWidget#mainNavigationContent QGroupBox QLabel {
    color: #b5bac1;
    font-size: 10px;
    font-weight: 500;
}
QWidget#mainNavigationContent QComboBox {
    min-height: 25px;
    color: #dbdee1;
    background: #1e1f22;
    border: 1px solid #3f4147;
    border-radius: 3px;
    padding: 0 7px;
}
QWidget#mainNavigationContent QPushButton {
    min-height: 25px;
    color: #dbdee1;
    background: #4e5058;
    border: none;
    border-radius: 3px;
    padding: 0 10px;
}
QWidget#mainNavigationContent QPushButton:hover {
    color: #ffffff;
    background: #5d5f68;
}
QWidget#mainNavigationContent QCheckBox {
    color: #dbdee1;
    spacing: 6px;
}
QWidget#mainNavigationContent QSlider::groove:horizontal {
    height: 4px;
    background: #1e1f22;
    border-radius: 2px;
}
QWidget#mainNavigationContent QSlider::handle:horizontal {
    width: 12px;
    margin: -4px 0;
    background: #5865f2;
    border-radius: 6px;
}
QLabel#mainNavigationPreview {
    color: #949ba4;
    background: #2b2d31;
    border: 1px solid #3f4147;
    border-radius: 4px;
    padding: 9px;
    font-size: 9px;
    font-weight: 600;
}
QLabel#mainNavigationBridgeState {
    color: #e0b96d;
    font-size: 11px;
    font-weight: 700;
    padding: 5px 0;
}
QLabel#mainNavigationBridgeState[connected="true"] {
    color: #74c991;
}
QLabel#mainNavigationBridgeState[offline="true"] {
    color: #77838d;
}
QFrame#mainNavigationDetails {
    background: #2b2d31;
    border: 1px solid #3f4147;
    border-radius: 5px;
}
QFrame#mainNavigationDetails QLabel {
    color: #949ba4;
    font-size: 10px;
}
QFrame#mainNavigationDetails QLabel#mainNavigationDetailValue {
    color: #dbdee1;
}
QLabel#mainNavigationDiagnostic {
    color: #6d6f78;
    background: #1e1f22;
    border-radius: 4px;
    padding: 8px;
    font-size: 9px;
}
QLabel#aboutProduct {
    color: #f2f3f5;
    font-size: 14px;
}
QWidget#aboutLinkRow {
    background: transparent;
}
QLabel#aboutLink {
    color: #b5bac1;
    font-size: 10px;
}
QPushButton#aboutSupportButton {
    min-height: 30px;
    padding: 0 13px;
    color: #ffffff;
    background: #5865f2;
    border: none;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
}
QPushButton#aboutSupportButton:hover {
    background: #4752c4;
}
QPushButton#aboutSupportButton:disabled {
    color: #82858f;
    background: #3f4147;
}
QToolButton#mainNavigationClose {
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: 0;
}
QToolButton#mainNavigationClose:hover {
    background: transparent;
    border: none;
}
QWidget#windowControls {
    background: transparent;
}
QFrame#windowControlsSeparator {
    background: rgba(111, 130, 145, 95);
    border: none;
}
QToolButton#windowMinimizeButton,
QToolButton#windowMaximizeButton,
QToolButton#windowCloseButton {
    background: transparent;
    color: #b9c5cf;
    border: none;
    border-radius: 0;
    font-size: 12px;
    padding: 0;
    margin: 0;
}
QToolButton#windowMinimizeButton:hover,
QToolButton#windowMaximizeButton:hover {
    background: transparent;
}
QToolButton#windowCloseButton:hover {
    background: transparent;
}
QToolButton#windowMinimizeButton:pressed,
QToolButton#windowMaximizeButton:pressed {
    background: transparent;
}
QToolButton#windowCloseButton:pressed {
    background: transparent;
}
QFrame#mapHelpSeparator {
    background: rgba(111, 130, 145, 80);
    border: none;
    max-height: 1px;
    margin-top: 4px;
    margin-bottom: 4px;
}
QLabel#mapHelpInfo {
    color: #aab8c4;
    font-size: 10px;
}
QLabel#mapHelpAuthor {
    color: #aab8c4;
    font-size: 10px;
}
QMenu {
    background: #18212a;
    color: #d6e0e8;
    border: 1px solid #3a4a58;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 10px;
    border-radius: 3px;
}
QMenu::item:selected {
    background: #2c4355;
    color: #ffffff;
}
QWidget#minimapRoot {
    background: #0b1016;
}
QWidget#minimapToolbar {
    background: #151d26;
    border: 1px solid #273340;
    border-radius: 7px;
}
QWidget#characterStatus {
    background: transparent;
}
QWidget#partyMemberStatus {
    background: rgba(25, 35, 45, 170);
    border-left: 1px solid #344352;
    border-radius: 4px;
}
QWidget#partyMemberStatus[empty="true"] {
    background: rgba(18, 26, 34, 105);
    border-left: 1px solid #2a3742;
}
QWidget#partyMemberStatus[empty="true"] QLabel#partyMemberTitle {
    color: #596875;
}
QWidget#partyMemberStatus[empty="true"] QLabel#partyClassIcon {
    color: #4d5b67;
}
QLabel#characterClassIcon {
    color: #eef3f7;
    background: transparent;
    border: none;
    font-size: 13px;
    font-weight: 700;
}
QLabel#partyClassIcon {
    color: #eef3f7;
    background: transparent;
    border: none;
    font-size: 11px;
    font-weight: 700;
}
QLabel#partyMemberTitle {
    color: #dce6ee;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
QLabel#characterTitle {
    color: #eef3f7;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QLabel#characterCombatIcon {
    color: #d58267;
    font-size: 11px;
    font-weight: 600;
}
QLabel#characterStatLabel {
    color: #8493a2;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.2px;
}
QLabel#characterVitalsText {
    color: #8493a2;
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.2px;
}
QWidget#riftStatus {
    background: transparent;
}
QLabel#riftTitle {
    color: #eef3f7;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
QLabel#riftCountdown {
    color: #8493a2;
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.2px;
}
QWidget#minimapSidebar {
    background: rgba(16, 23, 31, 218);
    border: 1px solid #3a4856;
    border-radius: 7px;
}
QScrollArea#sidebarScroll {
    background: transparent;
    border: none;
}
QScrollArea#sidebarScroll > QWidget > QWidget {
    background: transparent;
}
QScrollArea#sidebarScroll QScrollBar:vertical {
    width: 7px;
    margin: 1px 0;
    background: transparent;
}
QScrollArea#sidebarScroll QScrollBar::handle:vertical {
    min-height: 24px;
    border-radius: 3px;
    background: #425463;
}
QScrollArea#sidebarScroll QScrollBar::handle:vertical:hover {
    background: #587083;
}
QScrollArea#sidebarScroll QScrollBar::add-line:vertical,
QScrollArea#sidebarScroll QScrollBar::sub-line:vertical,
QScrollArea#sidebarScroll QScrollBar::add-page:vertical,
QScrollArea#sidebarScroll QScrollBar::sub-page:vertical {
    width: 0;
    height: 0;
    background: transparent;
}
QWidget#minimapSidebar QPushButton#sidebarHeaderButton {
    min-width: 0;
    min-height: 24px;
    max-height: 24px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 5px;
    color: #8493a2;
    background: transparent;
}
QWidget#minimapSidebar QPushButton#sidebarHeaderButton:hover {
    background: #202b36;
    border-color: #344352;
}
QWidget#minimapSidebar QPushButton#sidebarSectionButton {
    min-width: 0;
    min-height: 27px;
    max-height: 27px;
    padding: 0;
    border: 1px solid #3a4b5a;
    border-radius: 5px;
    color: #e4ebf1;
    background: rgba(31, 44, 56, 225);
}
QWidget#minimapSidebar QPushButton#sidebarSectionButton:hover {
    background: #293945;
    border-color: #587083;
}
QWidget#minimapSidebar QLabel#sidebarHeaderTitle {
    background: transparent;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QWidget#minimapSidebar QPushButton#sidebarSectionButton QLabel#sidebarHeaderTitle {
    color: #e4ebf1;
}
QWidget#minimapSidebar QLabel#sidebarHeaderArrow {
    color: #9cabb8;
    background: transparent;
    font-size: 9px;
    font-weight: 700;
}
QWidget#minimapSidebar QPushButton#sidebarHeaderButton QLabel#sidebarHeaderTitle {
    color: #8493a2;
    font-weight: 600;
}
QWidget#minimapSidebar QPushButton#sidebarSubItem {
    min-width: 0;
    min-height: 22px;
    max-height: 22px;
    padding: 0 8px 0 12px;
    text-align: left;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #b8c4cf;
    background: transparent;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0px;
}
QWidget#minimapSidebar QPushButton#sidebarSubItem[lootModeRow="true"] {
    padding-right: 43px;
}
QWidget#minimapSidebar QPushButton#sidebarSubItem:hover {
    color: #e4ebf1;
    background: #22303b;
    border-color: #3d5061;
}
QWidget#minimapSidebar QPushButton#sidebarSubItem:checked {
    color: #ffffff;
    background: #285f8b;
    border-color: #3979a9;
    font-weight: 600;
}
QWidget#minimapSidebar QPushButton#sidebarSubItem:disabled {
    color: #65727e;
    background: transparent;
    border-color: transparent;
}
QToolButton {
    min-width: 42px;
    min-height: 25px;
    padding: 1px 8px;
    border: 1px solid transparent;
    border-radius: 5px;
    color: #c8d2dc;
    background: transparent;
}
QToolButton:hover {
    background: #202b36;
    border-color: #344352;
}
QToolButton:checked {
    color: #ffffff;
    background: #285f8b;
    border-color: #3979a9;
}
QWidget#mapControlsOverlay {
    background: rgba(16, 23, 31, 218);
    border: 1px solid #3a4856;
    border-radius: 7px;
}
QWidget#mapControlsOverlay QToolButton#zoomButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 26px;
    max-height: 26px;
    padding: 0;
    color: #8493a2;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}
QWidget#mapControlsOverlay QToolButton#zoomButton:hover {
    background: #263440;
    border-color: #455769;
}
QLabel#zoomValue {
    color: #8493a2;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}
QWidget#mapControlsOverlay QToolButton#centerButton {
    min-height: 24px;
    max-height: 24px;
    padding: 0;
    text-align: center;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}
QWidget#mapControlsOverlay QToolButton#centerButton:hover {
    background: #263440;
    border-color: #455769;
}
QWidget#mapControlsOverlay QToolButton#centerButton:disabled {
    color: #687582;
    background: transparent;
}
QToolButton#mapHelpButton {
    min-width: 19px;
    max-width: 19px;
    min-height: 21px;
    max-height: 21px;
    padding: 0;
    border: none;
    border-radius: 0;
    color: #8493a2;
    background: transparent;
    font-size: 11px;
    font-weight: 700;
}
QToolButton#mapHelpButton:hover {
    color: #e4ebf1;
    background: transparent;
    border: none;
}
QToolButton#mapHelpButton:checked {
    color: #eaf2f8;
    background: #285f8b;
    border: none;
}
QToolButton#settingsButton {
    min-width: 19px;
    max-width: 19px;
    min-height: 21px;
    max-height: 21px;
    padding: 0;
    border: none;
    border-radius: 0;
    color: #8493a2;
    background: transparent;
}
QToolButton#settingsButton:hover {
    color: #e4ebf1;
    background: transparent;
    border: none;
}
QFrame#mapHelpPanel {
    background: rgba(16, 23, 31, 235);
    border: 1px solid #3a4856;
    border-radius: 7px;
}
QFrame#mapHelpPanel QLabel#mapHelpTitle {
    color: #e4ebf1;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding-bottom: 2px;
}
QFrame#mapHelpPanel QLabel#mapHelpKey {
    color: #9fb0be;
    font-size: 9px;
    font-weight: 600;
}
QFrame#mapHelpPanel QLabel#mapHelpAction {
    color: #c5d0da;
    font-size: 9px;
    font-weight: 500;
}
QFrame#dpsOverlay {
    background: rgba(12, 18, 24, 228);
    border: 1px solid #3a4856;
    border-radius: 7px;
}
QLabel#dpsOverlayTitle {
    color: #74c991;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.7px;
}
QLabel#dpsOverlayTitle[combat="true"] {
    color: #ef806f;
}
QLabel#dpsOverlaySummary {
    color: #eef3f7;
    font-size: 11px;
    font-weight: 700;
}
QLabel#dpsOverlaySkill {
    color: #b8c4cf;
    font-size: 9px;
    font-weight: 500;
}
QProgressBar#dpsOverlayBar {
    background: #111820;
    border: none;
    border-radius: 2px;
}
QProgressBar#dpsOverlayBar::chunk {
    background: #3478b7;
    border-radius: 2px;
}
QToolButton#dpsOverlayOpen {
    min-width: 19px;
    max-width: 19px;
    min-height: 17px;
    max-height: 17px;
    padding: 0;
    color: #9fb0be;
    border: 1px solid transparent;
    border-radius: 3px;
    background: transparent;
}
QToolButton#dpsOverlayOpen:hover {
    color: #ffffff;
    border-color: #455769;
    background: #263440;
}
QToolButton#dpsCollapsedButton {
    padding: 0;
    color: #e6edf3;
    border: 1px solid #3a4856;
    border-radius: 5px;
    background: rgba(12, 18, 24, 228);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QToolButton#dpsCollapsedButton:hover {
    color: #ffffff;
    border-color: #587083;
    background: #263440;
}
QWidget#minimapCanvas {
    background: #0d131a;
    border: 1px solid #273340;
}
QWidget#minimapFooter {
    background: transparent;
}
QLabel#connectionStatus {
    color: #e0b96d;
}
QLabel#connectionStatus[status="connected"] {
    color: #74c991;
}
QLabel#connectionStatus[status="waiting"] {
    color: #e0b96d;
}
QLabel#connectionStatus[status="failure"] {
    color: #ef806f;
}
QLabel#connectionStatus[status="offline"] {
    color: #77838d;
}
QLabel#positionStatus {
    color: #8f9caa;
}
QLabel#characterOfflineLabel {
    color: #77838d;
    font-size: 10px;
    font-weight: 600;
}
"""
