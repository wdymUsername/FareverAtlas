"""Centralized Qt style sheets for Farever Atlas."""

MAP_WINDOW_STYLESHEET = r"""
/* Discreet scrollbars — thin handle, no arrows, transparent track. */
QScrollBar:vertical {
    width: 7px;
    margin: 1px 0;
    background: transparent;
    border: none;
}
QScrollBar::handle:vertical {
    min-height: 24px;
    border-radius: 3px;
    background: #425463;
}
QScrollBar::handle:vertical:hover {
    background: #587083;
}
QScrollBar::handle:vertical:pressed {
    background: #6a8496;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    width: 0;
    height: 0;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
}
QScrollBar:horizontal {
    height: 7px;
    margin: 0 1px;
    background: transparent;
    border: none;
}
QScrollBar::handle:horizontal {
    min-width: 24px;
    border-radius: 3px;
    background: #425463;
}
QScrollBar::handle:horizontal:hover {
    background: #587083;
}
QScrollBar::handle:horizontal:pressed {
    background: #6a8496;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    width: 0;
    height: 0;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
}

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
QToolButton#mainMenuButton,
QToolButton#reloadUiButton {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}
QToolButton#mainMenuButton:hover,
QToolButton#mainMenuButton:pressed,
QToolButton#reloadUiButton:hover,
QToolButton#reloadUiButton:pressed {
    background: transparent;
    border: none;
}
QToolButton#reloadUiButton:disabled {
    opacity: 0.45;
}
QToolButton#mainMenuButton::menu-indicator {
    image: none;
    width: 0;
}
QToolButton#mapPageButton,
QToolButton#plannerPageButton,
QToolButton#codexPageButton,
QToolButton#playersPageButton {
    color: #8493a2;
    background: transparent;
    border: none;
    border-radius: 3px;
    padding: 0 7px;
    font-size: 10px;
    font-weight: 600;
}
QToolButton#mapPageButton:hover,
QToolButton#plannerPageButton:hover,
QToolButton#codexPageButton:hover,
QToolButton#playersPageButton:hover {
    color: #dce6ee;
    background: #202b36;
}
QToolButton#mapPageButton:checked,
QToolButton#plannerPageButton:checked,
QToolButton#codexPageButton:checked,
QToolButton#playersPageButton:checked {
    color: #eef3f7;
    background: #2a3946;
}
QWidget#mapPage,
QWidget#plannerPage,
QWidget#codexPage,
QWidget#playersPage,
QStackedWidget#mainPageStack {
    background: transparent;
    border: none;
}
QWidget#plannerContentPlaceholder {
    background: transparent;
    border: none;
}
QLabel#codexPlaceholder,
QLabel#playersPlaceholder {
    color: #8493a2;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
    border: none;
}
QWidget#playersColumn {
    background: transparent;
    border: none;
}
QWidget#playersColumnsHost {
    background: transparent;
    border: none;
}
QWidget#playersColumnGutter {
    background: transparent;
    border: none;
    border-left: 1px solid #24303a;
    border-right: 1px solid #24303a;
    margin: 4px 0;
}
QLabel#playersColumnTitle {
    color: #9aabba;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    background: transparent;
    border: none;
    padding: 6px 8px 4px 8px;
}
QWidget#plannerToolbar,
QWidget#codexToolbar,
QWidget#playersToolbar {
    background: #151d26;
    border: 1px solid #273340;
    border-radius: 7px;
}
QLabel#playersSummaryLabel {
    color: #dce6ee;
    font-size: 10px;
    font-weight: 600;
    background: transparent;
    border: none;
    padding-left: 4px;
}
QLineEdit#playersSearchField,
QComboBox#playersSortCombo {
    color: #dce6ee;
    background: #10171e;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 0 7px;
    font-size: 10px;
}
QLineEdit#playersSearchField:hover,
QLineEdit#playersSearchField:focus,
QComboBox#playersSortCombo:hover,
QComboBox#playersSortCombo:focus {
    border-color: #587083;
    background: #141e27;
}
QComboBox#playersSortCombo::drop-down {
    width: 16px;
    border: none;
}
QComboBox#playersSortCombo QAbstractItemView {
    color: #dce6ee;
    background: #18212a;
    border: 1px solid #3a4a58;
    selection-background-color: #2c4355;
    selection-color: #ffffff;
    outline: none;
}
QToolButton#playersPartyOnlyButton,
QToolButton#playersClassPinButton {
    color: #8493a2;
    background: #10171e;
    border: 1px solid #344352;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
}
QToolButton#playersClassPinButton {
    padding: 0;
}
QToolButton#playersPartyOnlyButton:hover,
QToolButton#playersClassPinButton:hover {
    color: #dce6ee;
    border-color: #587083;
    background: #141e27;
}
QToolButton#playersPartyOnlyButton:checked,
QToolButton#playersClassPinButton:checked {
    color: #eef3f7;
    background: #2a3946;
    border-color: #4a6275;
}
QScrollArea#playersScroll,
QWidget#playersListHost {
    background: transparent;
    border: none;
}
QFrame#playersListRow {
    background: #121920;
    border: 1px solid #24303a;
    border-radius: 5px;
}
QFrame#playersListRow:hover {
    background: #18212a;
    border-color: #344352;
}
QFrame#playersListRow[selected="true"] {
    background: #1c2a36;
    border-color: #4a6275;
}
QLabel#playersRowClassIcon {
    background: transparent;
    border: none;
    color: #8493a2;
    font-size: 12px;
}
QLabel#playersRowName {
    color: #eef3f7;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border: none;
}
QLabel#playersRowMeta {
    color: #8493a2;
    font-size: 10px;
    background: transparent;
    border: none;
}
QLabel#playersRowUid {
    color: #6f8192;
    font-size: 10px;
    font-family: monospace;
    background: transparent;
    border: none;
}
QLabel#playersRowDistance {
    color: #9eb0c0;
    font-size: 10px;
    font-weight: 600;
    background: transparent;
    border: none;
}
QLabel#playersRowBadgeYou,
QLabel#playersRowBadgeParty,
QLabel#playersRowBadgePresence,
QLabel#playersRowBadgeSteam,
QLabel#playersRowBadgeSteamFriend {
    color: #dce6ee;
    background: #2a3946;
    border: none;
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#playersRowBadgeYou {
    background: #315d7c;
}
QLabel#playersRowBadgeParty {
    background: #3a4d3f;
    color: #b8d9c0;
}
QLabel#playersRowBadgePresence[presence="here"] {
    background: #2a4a36;
    color: #d9f0df;
}
QLabel#playersRowBadgePresence[presence="away"] {
    background: #2a323a;
    color: #c5ced6;
}
QLabel#playersRowBadgeSteam {
    background: #24303a;
    color: #b8c6d2;
}
QLabel#playersRowBadgeSteam[steamState="private"] {
    background: #3a3426;
    color: #e6d4a8;
}
QLabel#playersRowBadgeSteamFriend {
    background: #1e3a4a;
    color: #9ec9e0;
}
QToolButton#playersRowProfileButton,
QToolButton#playersRowFocusButton,
QToolButton#playersRowFriendButton {
    color: #8493a2;
    background: #10171e;
    border: 1px solid #344352;
    border-radius: 4px;
    font-size: 9px;
    font-weight: 600;
}
QToolButton#playersRowFriendButton[friendActive="true"] {
    color: #e6d4a8;
    border-color: #6a5a3a;
}
QToolButton#playersRowProfileButton:hover,
QToolButton#playersRowFocusButton:hover,
QToolButton#playersRowFriendButton:hover {
    color: #dce6ee;
    border-color: #587083;
    background: #141e27;
}
QToolButton#playersRowProfileButton:disabled,
QToolButton#playersRowFocusButton:disabled,
QToolButton#playersRowFriendButton:disabled {
    color: #556270;
    background: #10171e;
    border-color: #2a3540;
}
QWidget#plannerLevelSelector {
    background: #10171e;
    border: 1px solid #344352;
    border-radius: 4px;
}
QWidget#plannerLevelSelector:hover {
    border-color: #587083;
    background: #141e27;
}
QComboBox#plannerLevelCombo,
QLineEdit#plannerBuildName {
    color: #dce6ee;
    background: #10171e;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 0 7px;
    font-size: 10px;
}
QComboBox#plannerLevelCombo {
    background: transparent;
    border: none;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    padding-left: 8px;
    font-weight: 600;
}
QComboBox#plannerLevelCombo:hover,
QComboBox#plannerLevelCombo:focus {
    background: transparent;
    border: none;
}
QComboBox#plannerLevelCombo::drop-down {
    width: 0;
    border: none;
}
QComboBox#plannerLevelCombo::down-arrow {
    image: none;
    width: 0;
    height: 0;
}
QComboBox#plannerLevelCombo QAbstractItemView {
    color: #dce6ee;
    background: #18212a;
    border: 1px solid #3a4a58;
    selection-background-color: #2c4355;
    selection-color: #ffffff;
    outline: none;
}
QComboBox#plannerClassSelector:hover,
QLineEdit#plannerBuildName:hover,
QLineEdit#plannerBuildName:focus {
    border-color: #587083;
    background: #141e27;
}
QWidget#plannerLevelStepColumn {
    background: transparent;
    border-left: 1px solid #344352;
}
QToolButton#plannerLevelPlusButton,
QToolButton#plannerLevelMinusButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 16px;
    max-height: 16px;
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    margin: 0;
}
QToolButton#plannerLevelPlusButton:hover,
QToolButton#plannerLevelMinusButton:hover {
    background: #263541;
}
QToolButton#plannerLevelPlusButton:pressed,
QToolButton#plannerLevelMinusButton:pressed {
    background: #314454;
}
QToolButton#plannerLevelPlusButton:disabled,
QToolButton#plannerLevelMinusButton:disabled {
    background: transparent;
}
QWidget#plannerClassSelectorShell {
    background: transparent;
    border: none;
}
QLabel#plannerClassBadge {
    background: transparent;
    border: none;
}
QFrame#plannerClassPopup {
    background: #18212a;
    border: 1px solid #3a4a58;
    border-radius: 4px;
}
QToolButton#plannerClassPopupRow {
    min-width: 176px;
    max-width: 176px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
    margin: 0;
    color: #dce6ee;
    background: transparent;
    border: none;
    border-radius: 0;
    font-size: 10px;
    text-align: center;
}
QToolButton#plannerClassPopupRow:hover {
    background: #253746;
    color: #ffffff;
}
QToolButton#plannerClassPopupRow[selected="true"],
QToolButton#plannerClassPopupRow:checked {
    background: #2c4355;
    color: #ffffff;
}
QLineEdit#plannerBuildName::placeholder {
    color: #667684;
}
QToolButton#plannerSaveButton,
QToolButton#plannerLoadButton,
QToolButton#plannerResetButton {
    color: #b9c5cf;
    background: #10171e;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 0 8px;
    font-size: 10px;
    font-weight: 600;
}
QToolButton#plannerSaveButton:hover,
QToolButton#plannerLoadButton:hover,
QToolButton#plannerResetButton:hover {
    color: #eef3f7;
    border-color: #587083;
    background: #1b2833;
}
QToolButton#plannerSaveButton:pressed,
QToolButton#plannerLoadButton:pressed,
QToolButton#plannerResetButton:pressed {
    background: #263541;
}
QToolButton#plannerSaveButton[confirmOverwrite="true"] {
    color: #ffffff;
    background: #6e2833;
    border-color: #c35c6c;
}
QToolButton#plannerSaveButton[confirmOverwrite="true"]:hover {
    color: #ffffff;
    background: #842f3d;
    border-color: #e17887;
}
QToolButton#onlineModeSwitch {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}
QToolButton#onlineModeSwitch:hover,
QToolButton#onlineModeSwitch:pressed,
QToolButton#onlineModeSwitch:checked {
    background: transparent;
    border: none;
}
QToolButton#onlineModeSwitch:focus {
    border: none;
}
QToolButton#onlineModeSwitch::menu-indicator {
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
    color: #8b9bab;
    font-size: 10px;
    font-weight: 600;
}
QLabel#settingsDeferredNote {
    color: #8b9bab;
    font-size: 10px;
    padding: 4px 2px 0 2px;
}
QLabel#mainNavigationPreview {
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
    color: #949ba4;
    font-size: 10px;
}
QPushButton#bridgeDiagnosticsButton,
QPushButton#resetAllSettingsButton {
    color: #d7dee6;
    background: #1b222b;
    border: 1px solid #3a4a58;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 10px;
    font-weight: 600;
}
QPushButton#bridgeDiagnosticsButton:hover,
QPushButton#resetAllSettingsButton:hover {
    background: #24313c;
    border-color: #557083;
}
QPushButton#resetAllSettingsButton[confirmReset="true"] {
    color: #ffffff;
    background: #6e2833;
    border-color: #c35c6c;
}
QPushButton#resetAllSettingsButton[confirmReset="true"]:hover {
    color: #ffffff;
    background: #842f3d;
    border-color: #e17887;
}
QPushButton#aboutSupportButton {
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
QWidget#gameTimeStatus {
    background: transparent;
}
QLabel#gameTimeIcon {
    color: #eef3f7;
    background: transparent;
    border: none;
    font-size: 20px;
    font-weight: 600;
}
QLabel#gameTimeLabel {
    color: #eef3f7;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QWidget#minimapSidebar {
    background: rgba(16, 23, 31, 218);
    border: 1px solid #3a4856;
    border-radius: 7px;
}
QWidget#sidebarSegmentBar {
    background: transparent;
    border: none;
    border-bottom: 1px solid #2e3e4b;
}
QWidget#minimapSidebar QPushButton#sidebarSegmentButton {
    min-width: 0;
    min-height: 22px;
    max-height: 22px;
    padding: 0 4px;
    color: #7f929f;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.4px;
}
QWidget#minimapSidebar QPushButton#sidebarSegmentButton:hover {
    color: #d8e3e9;
}
QWidget#minimapSidebar QPushButton#sidebarSegmentButton:checked {
    color: #eef4f8;
    border-bottom: 2px solid #6f8fa3;
}
QLabel#sidebarFilterHint {
    color: #667682;
    background: transparent;
    border: none;
    font-size: 8px;
    font-weight: 500;
    letter-spacing: 0.2px;
}
QLabel#gatherNavFieldLabel {
    color: #7f91a0;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.6px;
    background: transparent;
    border: none;
}
QToolButton#gatherSidebarFab,
QToolButton#fowToolsFab {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    margin: 0;
    border: 1px solid #3a4856;
    border-radius: 6px;
    background: rgba(16, 23, 31, 218);
    color: #b9c5cf;
}
QToolButton#gatherSidebarFab:hover,
QToolButton#fowToolsFab:hover {
    background: #202b36;
    border-color: #55778f;
}
QWidget#gatherSidebarHeader,
QWidget#fowToolsHeader {
    background: transparent;
    border: none;
    min-height: 22px;
}
QLabel#gatherSidebarHeaderIcon,
QLabel#fowToolsHeaderIcon {
    background: transparent;
    border: none;
}
QLabel#gatherSidebarTitle,
QLabel#fowToolsTitle {
    color: #8493a2;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
    border: none;
}
QToolButton#gatherSidebarCloseButton,
QToolButton#fowToolsCloseButton {
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 0;
    margin: 0;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
    color: #9cabb8;
}
QToolButton#gatherSidebarCloseButton:hover,
QToolButton#fowToolsCloseButton:hover {
    background: #202b36;
    border-color: #344352;
    color: #e4ebf1;
}
QToolButton#gatherNavSidebarButton {
    color: #b9c5cf;
    background: #111922;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 0 8px;
    font-size: 9px;
    font-weight: 600;
}
QToolButton#gatherNavSidebarButton:hover {
    color: #ffffff;
    background: #203546;
    border-color: #55778f;
}
QToolButton#gatherNavSidebarButton:checked {
    color: #eef4f8;
    background: #203546;
    border-color: #6a8da5;
}
QToolButton#gatherNavSidebarButton:disabled {
    color: #667682;
    background: #10171e;
    border-color: #293945;
}
QScrollArea#sidebarScroll {
    background: transparent;
    border: none;
}
QScrollArea#sidebarScroll > QWidget > QWidget {
    background: transparent;
}
QScrollArea#customFilterScroll {
    background: transparent;
    border: none;
}
QScrollArea#customFilterScroll > QWidget > QWidget {
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
QWidget#minimapSidebar QPushButton#sidebarFilterChip {
    min-width: 0;
    min-height: 24px;
    max-height: 24px;
    padding: 0 8px;
    text-align: left;
    border: 1px solid #3a4b5a;
    border-radius: 5px;
    color: #9aabb8;
    background: transparent;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0px;
}
QWidget#minimapSidebar QPushButton#sidebarFilterChip[hasDot="true"] {
    padding-left: 18px;
}
QWidget#minimapSidebar QPushButton#sidebarFilterChip[multiDot="true"] {
    padding-left: 32px;
}
QWidget#minimapSidebar QPushButton#sidebarFilterChip:hover {
    color: #e4ebf1;
    background: #22303b;
    border-color: #3d5061;
}
QWidget#minimapSidebar QPushButton#sidebarFilterChip:checked {
    color: #ffffff;
    background: #285f8b;
    border-color: #3979a9;
    font-weight: 600;
}
QWidget#minimapSidebar QPushButton#sidebarFilterChip:disabled {
    color: #65727e;
    background: transparent;
    border-color: #2a3641;
}
QFrame#sidebarFilterSeparator {
    background: #2e3e4b;
    border: none;
    max-height: 1px;
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
QWidget#mapControlsOverlay,
QWidget#mapFowEditOverlay {
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
QWidget#mapControlsOverlay QToolButton#centerButton,
QWidget#mapFowEditOverlay QToolButton#centerButton,
QWidget#mapFowEditOverlay QToolButton#fowEditButton {
    min-height: 24px;
    max-height: 24px;
    padding: 0 4px;
    text-align: center;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #b7c3cf;
    background: #1a242e;
    border: 1px solid #3a4856;
    border-radius: 4px;
}
QWidget#mapControlsOverlay QToolButton#centerButton:hover,
QWidget#mapFowEditOverlay QToolButton#centerButton:hover,
QWidget#mapFowEditOverlay QToolButton#fowEditButton:hover {
    color: #e4ebf1;
    background: #263440;
    border-color: #455769;
}
QWidget#mapControlsOverlay QToolButton#centerButton:checked,
QWidget#mapFowEditOverlay QToolButton#centerButton:checked,
QWidget#mapFowEditOverlay QToolButton#fowEditButton:checked {
    color: #ffffff;
    background: #285f8b;
    border-color: #3979a9;
}
QWidget#mapControlsOverlay QToolButton#centerButton:disabled,
QWidget#mapFowEditOverlay QToolButton#centerButton:disabled,
QWidget#mapFowEditOverlay QToolButton#fowEditButton:disabled {
    color: #687582;
    background: #151c24;
    border-color: #2c3845;
}
QWidget#mapFowEditOverlay QToolButton#fowEditButton[inverted="true"] {
    border-color: #c48a3a;
}
QWidget#mapFowEditOverlay QToolButton#fowEditButton[inverted="true"]:checked {
    border-color: #e0a84a;
}
QLabel#fowEditSection {
    color: #6f7f90;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 2px 0 0 0;
}
QLabel#fowEditStatus {
    color: #8493a2;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
    padding: 2px 0;
}
QComboBox#fowEditCombo {
    min-height: 24px;
    max-height: 24px;
    padding: 0 6px;
    color: #b7c3cf;
    font-size: 10px;
    font-weight: 600;
    background: #1a242e;
    border: 1px solid #3a4856;
    border-radius: 4px;
}
QComboBox#fowEditCombo:hover,
QComboBox#fowEditCombo:focus {
    border-color: #455769;
    color: #e4ebf1;
}
QComboBox#fowEditCombo::drop-down {
    width: 16px;
    border: none;
}
QComboBox#fowEditCombo QAbstractItemView {
    background: #1a242e;
    color: #e4ebf1;
    border: 1px solid #3a4856;
    selection-background-color: #285f8b;
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

QFrame#plannerBuildLoadOverlay {
    background: #0b1016;
    border: 1px solid #344352;
    border-radius: 8px;
}
QLabel#plannerBuildDialogTitle {
    color: #e7eef4;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}
QToolButton#plannerBuildDialogClose {
    color: #aebbc6;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 18px;
    font-weight: 500;
}
QToolButton#plannerBuildDialogClose:hover {
    color: #ffffff;
    background: #1b2833;
    border-color: #3f5262;
}
QFrame#plannerBuildListHeader {
    min-height: 30px;
    max-height: 30px;
    background: #111922;
    border: 1px solid #2d3c49;
    border-radius: 4px;
}
QLabel#plannerBuildColumnHeader {
    color: #7f91a0;
    font-size: 9px;
    font-weight: 700;
}
QScrollArea#plannerBuildScrollArea,
QWidget#plannerBuildList {
    background: transparent;
    border: none;
}
QFrame#plannerBuildRow {
    min-height: 42px;
    max-height: 42px;
    background: #10171e;
    border: 1px solid #293945;
    border-radius: 4px;
}
QFrame#plannerBuildRow:hover {
    background: #141e27;
    border-color: #3d5262;
}
QLabel#plannerBuildRowName {
    color: #dce6ee;
    font-size: 10px;
    font-weight: 600;
}
QLabel#plannerBuildRowClass {
    color: #b9c6d0;
    font-size: 9px;
    font-weight: 600;
}
QLabel#plannerBuildRowDate {
    color: #91a1ad;
    font-size: 9px;
}
QLabel#plannerBuildEmptyState {
    color: #758692;
    font-size: 10px;
}
QToolButton#plannerBuildDeleteButton,
QToolButton#plannerBuildLoadButton {
    color: #b9c5cf;
    background: #111922;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 0 7px;
    font-size: 9px;
    font-weight: 600;
}
QToolButton#plannerBuildDeleteButton:hover {
    color: #ffd7d7;
    background: #352126;
    border-color: #83505a;
}
QToolButton#plannerBuildDeleteButton[confirmDelete="true"] {
    color: #ffffff;
    background: #6e2833;
    border-color: #c35c6c;
}
QToolButton#plannerBuildDeleteButton[confirmDelete="true"]:hover {
    color: #ffffff;
    background: #842f3d;
    border-color: #e17887;
}
QToolButton#plannerBuildLoadButton:hover {
    color: #ffffff;
    background: #203546;
    border-color: #55778f;
}
QToolButton#plannerBuildDeleteButton:pressed,
QToolButton#plannerBuildLoadButton:pressed {
    background: #263541;
}

QFrame#waypointManagerOverlay,
QFrame#waypointEditOverlay,
QFrame#waypointConfirmOverlay {
    background: #0b1016;
    border: 1px solid #344352;
    border-radius: 8px;
}
QWidget#gatherNavPanel {
    background: transparent;
    border: none;
}
QComboBox#gatherNavCombo {
    color: #dce6ee;
    background: #111922;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 22px;
    font-size: 10px;
}
QComboBox#gatherNavCombo:hover {
    border-color: #55778f;
}
QComboBox#gatherNavCombo::drop-down {
    border: none;
    width: 18px;
}
QComboBox#gatherNavCombo QAbstractItemView {
    color: #dce6ee;
    background: #111922;
    border: 1px solid #344352;
    selection-background-color: #203546;
    outline: none;
}
QFrame#gatherNavStatus {
    background: #10171e;
    border: 1px solid #293945;
    border-radius: 4px;
}
QLabel#gatherNavStatusTitle {
    color: #dce6ee;
    font-size: 10px;
    font-weight: 700;
    background: transparent;
    border: none;
}
QLabel#gatherNavStatusDetail {
    color: #91a1ad;
    font-size: 9px;
    background: transparent;
    border: none;
}
QFrame#waypointEditOverlay QLabel {
    color: #aab9c5;
    font-size: 10px;
    background: transparent;
    border: none;
}
QLabel#waypointOverlayTitle {
    color: #e7eef4;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}
QToolButton#waypointOverlayClose {
    color: #aebbc6;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 18px;
    font-weight: 500;
}
QToolButton#waypointOverlayClose:hover {
    color: #ffffff;
    background: #1b2833;
    border-color: #3f5262;
}
QLabel#waypointStoragePath {
    color: #758692;
    font-size: 9px;
    background: transparent;
    border: none;
}
QLabel#waypointOverlayBody {
    color: #c5d0d8;
    font-size: 11px;
    background: transparent;
    border: none;
}
QLabel#waypointOverlayError {
    color: #e17887;
    font-size: 10px;
    background: transparent;
    border: none;
}
QFrame#waypointListHeader {
    min-height: 30px;
    max-height: 30px;
    background: #111922;
    border: 1px solid #2d3c49;
    border-radius: 4px;
}
QLabel#waypointColumnHeader {
    color: #7f91a0;
    font-size: 9px;
    font-weight: 700;
}
QScrollArea#waypointScrollArea,
QWidget#waypointList {
    background: transparent;
    border: none;
}
QFrame#waypointRow {
    min-height: 42px;
    max-height: 42px;
    background: #10171e;
    border: 1px solid #293945;
    border-radius: 4px;
}
QFrame#waypointRow:hover {
    background: #141e27;
    border-color: #3d5262;
}
QLabel#waypointRowName {
    color: #dce6ee;
    font-size: 10px;
    font-weight: 600;
}
QLabel#waypointRowMeta {
    color: #91a1ad;
    font-size: 9px;
}
QLabel#waypointEmptyState {
    color: #758692;
    font-size: 10px;
}
QToolButton#waypointRowButton,
QToolButton#waypointRowDeleteButton,
QToolButton#waypointOverlayPrimaryButton,
QToolButton#waypointOverlaySecondaryButton,
QToolButton#waypointOverlayDangerButton {
    color: #b9c5cf;
    background: #111922;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 0 10px;
    font-size: 9px;
    font-weight: 600;
}
QToolButton#waypointRowButton:hover,
QToolButton#waypointOverlaySecondaryButton:hover {
    color: #ffffff;
    background: #203546;
    border-color: #55778f;
}
QToolButton#waypointOverlayPrimaryButton {
    color: #eef4f8;
    background: #203546;
    border-color: #55778f;
}
QToolButton#waypointOverlayPrimaryButton:hover {
    color: #ffffff;
    background: #2a4558;
    border-color: #6a8da5;
}
QToolButton#waypointRowDeleteButton:hover,
QToolButton#waypointOverlayDangerButton:hover {
    color: #ffd7d7;
    background: #352126;
    border-color: #83505a;
}
QToolButton#waypointOverlayDangerButton {
    color: #ffd7d7;
    background: #352126;
    border-color: #83505a;
}
QToolButton#waypointRowDeleteButton[confirmDelete="true"] {
    color: #ffffff;
    background: #6e2833;
    border-color: #c35c6c;
}
QToolButton#waypointRowDeleteButton[confirmDelete="true"]:hover {
    color: #ffffff;
    background: #842f3d;
    border-color: #e17887;
}
QLineEdit#waypointOverlayField,
QDoubleSpinBox#waypointOverlayField,
QComboBox#waypointOverlayField {
    color: #e7eef4;
    background: #111922;
    border: 1px solid #344352;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 26px;
}
QLineEdit#waypointOverlayField:focus,
QDoubleSpinBox#waypointOverlayField:focus,
QComboBox#waypointOverlayField:focus {
    border-color: #55778f;
}
QComboBox#waypointOverlayField::drop-down {
    border: none;
    width: 20px;
}

QSplitter#plannerMainSplitter,
QSplitter#plannerEquipmentSplitter {
    background: transparent;
    border: none;
}
QSplitter#plannerMainSplitter::handle,
QSplitter#plannerEquipmentSplitter::handle {
    background: transparent;
}
QSplitter#plannerMainSplitter::handle:hover,
QSplitter#plannerEquipmentSplitter::handle:hover {
    background: #1d2b35;
}
QFrame#plannerStatsPanel,
QFrame#plannerArmorPanel,
QFrame#plannerWeaponsPanel,
QFrame#plannerProgressionPanel {
    background: #0d141b;
    border: 1px solid #2e3e4b;
    border-radius: 5px;
}
QLabel#plannerPanelHeader {
    color: #9eafbc;
    background: #111a22;
    border: none;
    border-bottom: 1px solid #2e3e4b;
    padding-left: 12px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QWidget#plannerStatsContent,
QWidget#plannerArmorContent,
QWidget#plannerWeaponsContent,
QWidget#plannerClassSkillsContent,
QWidget#plannerTalentsContent {
    background: transparent;
    border: none;
}

QWidget#plannerStatRow {
    min-height: 21px;
    max-height: 21px;
    background: transparent;
    border: none;
}
QLabel#plannerStatLabel {
    color: #9eafbc;
    font-size: 10px;
}
QLabel#plannerStatValue {
    color: #e3ebf1;
    font-size: 10px;
    font-weight: 700;
}
QFrame#plannerStatsDivider {
    background: #2d3d49;
    border: none;
}
QToolButton#plannerEquipmentSlot {
    color: #9eafbc;
    background: #111922;
    border: 1px solid #31424f;
    border-radius: 5px;
    padding: 8px;
    font-size: 10px;
    font-weight: 600;
}
QToolButton#plannerEquipmentSlot:hover {
    color: #eef4f8;
    background: #17242e;
    border-color: #536d80;
}
QToolButton#plannerEquipmentSlot:pressed {
    background: #20313d;
    border-color: #66879d;
}

QScrollArea#plannerClassSkillsScroll {
    background: transparent;
    border: none;
}
QToolButton#plannerClassSkillSlot {
    background: #111922;
    border: 1px solid #31424f;
    border-radius: 5px;
    padding: 0;
}
QLabel#plannerClassSkillTitle {
    color: #aab9c5;
    background: transparent;
    border: none;
    font-size: 10px;
    font-weight: 600;
}
QToolButton#plannerClassSkillSlot:hover {
    color: #eef4f8;
    background: #17242e;
    border-color: #536d80;
}
QToolButton#plannerClassSkillSlot:pressed {
    background: #20313d;
    border-color: #66879d;
}

QWidget#plannerTalentPointsRow {
    background: #101820;
    border: none;
    border-bottom: 1px solid #2e3e4b;
}
QLabel#plannerTalentPointsCaption {
    color: #9eafbc;
    font-size: 10px;
    font-weight: 600;
}
QLabel#plannerTalentPointsValue {
    color: #d7e66d;
    font-size: 11px;
    font-weight: 700;
}
QScrollArea#plannerTalentsScroll {
    background: transparent;
    border: none;
}
QWidget#plannerTalentTree {
    background: transparent;
    border: none;
}
QToolButton#plannerTalentChoice {
    color: #aab9c5;
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    font-size: 9px;
    font-weight: 700;
}
QToolButton#plannerTalentChoice:hover {
    color: #f1f6f9;
    background: transparent;
    border: none;
}
QToolButton#plannerTalentChoice:pressed {
    color: #ffffff;
    background: transparent;
    border: none;
}
QLabel#plannerTalentRank {
    color: #d6e0e6;
    background: transparent;
    border: none;
    font-size: 9px;
    font-weight: 700;
}

QTabWidget#plannerProgressionTabs {
    background: transparent;
    border: none;
}
QTabWidget#plannerProgressionTabs::pane {
    background: transparent;
    border: none;
    top: 0;
}
QTabWidget#plannerProgressionTabs QTabBar {
    background: #111a22;
    border: none;
    border-bottom: 1px solid #2e3e4b;
}
QTabWidget#plannerProgressionTabs QTabBar::tab {
    min-height: 33px;
    color: #7f929f;
    background: #111a22;
    border: none;
    border-right: 1px solid #2e3e4b;
    padding: 0 12px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QTabWidget#plannerProgressionTabs QTabBar::tab:last {
    border-right: none;
}
QTabWidget#plannerProgressionTabs QTabBar::tab:hover {
    color: #d8e3e9;
    background: #17232d;
}
QTabWidget#plannerProgressionTabs QTabBar::tab:selected {
    color: #eef4f8;
    background: #17232d;
    border-bottom: 2px solid #6f8fa3;
}
QWidget#plannerClassSkillsPage,
QWidget#plannerTalentsPage {
    background: transparent;
    border: none;
}

QToolButton#plannerProgressionCollapseButton {
    color: #8fa2ae;
    background: #111a22;
    border: none;
    border-left: 1px solid #2e3e4b;
    padding: 0;
    font-size: 15px;
    font-weight: 700;
}
QToolButton#plannerProgressionCollapseButton:hover {
    color: #eef4f8;
    background: #1a2933;
}
QToolButton#plannerProgressionExpandButton {
    color: #8fa2ae;
    background: #111a22;
    border: none;
    padding: 0;
    font-size: 17px;
    font-weight: 700;
}
QToolButton#plannerProgressionExpandButton:hover {
    color: #eef4f8;
    background: #1a2933;
}
QToolButton#plannerClassSkillSlot[locked="true"] {
    background: #0b1117;
    border-color: #202d36;
}
QToolButton#plannerClassSkillSlot[locked="true"]:hover {
    background: #0b1117;
    border-color: #202d36;
}
QLabel#plannerClassSkillTitle[locked="true"] {
    color: #52616b;
}
QLabel#plannerClassSkillTitle[locked="false"] {
    color: #aab9c5;
}

QLabel#plannerClassSkillUnlockNote {
    color: #687985;
    background: transparent;
    border: none;
    font-size: 9px;
    font-weight: 500;
}

QToolButton#plannerTalentChoice[ranked="true"] {
    color: #eef4f8;
    background: transparent;
    border: none;
}
QToolButton#plannerTalentChoice[ranked="true"]:hover {
    color: #ffffff;
    background: transparent;
    border: none;
}

QWidget#toastHost {
    background: transparent;
    border: none;
}
QFrame#toastCard {
    background: #152029;
    border: 1px solid #3a5160;
    border-radius: 6px;
    min-height: 36px;
}
QFrame#toastCard[toastKind="success"] {
    border-color: #3d6b52;
    background: #14241c;
}
QFrame#toastCard[toastKind="warning"] {
    border-color: #7a6230;
    background: #241e12;
}
QFrame#toastCard[toastKind="error"] {
    border-color: #7a3a3a;
    background: #241414;
}
QFrame#toastCard[toastKind="info"] {
    border-color: #3a5160;
    background: #152029;
}
QLabel#toastMessage {
    color: #e8f0f6;
    background: transparent;
    border: none;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#toastClose {
    color: #8fa2ae;
    background: transparent;
    border: none;
    padding: 0;
    font-size: 14px;
    font-weight: 700;
}
QToolButton#toastClose:hover {
    color: #eef4f8;
}
"""
