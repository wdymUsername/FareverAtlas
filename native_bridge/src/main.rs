// Release builds are a headless Windows PE (no console window). Debug keeps a
// console so one-shot discovery and attach errors stay visible while developing.
#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

#[cfg(not(windows))]
fn main() {
    eprintln!(
        "farever-atlas-bridge must be built for Windows and run inside Farever's Proton prefix"
    );
    std::process::exit(2);
}

#[cfg(windows)]
mod windows_bridge {
    use std::collections::{HashMap, HashSet};
    use std::ffi::{OsString, c_void};
    use std::mem::{size_of, zeroed};
    use std::os::windows::ffi::OsStringExt;
    use std::path::Path;
    use std::ptr::NonNull;
    use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

    type Bool = i32;
    type Dword = u32;
    type Handle = *mut c_void;
    type Long = i32;
    type UlongPtr = usize;

    const FALSE: Bool = 0;
    const MAX_PATH: usize = 260;
    const MAX_MODULE_NAME32: usize = 255;
    const INVALID_HANDLE_VALUE: Handle = -1_isize as Handle;

    const TH32CS_SNAPPROCESS: Dword = 0x0000_0002;
    const TH32CS_SNAPMODULE: Dword = 0x0000_0008;
    const TH32CS_SNAPMODULE32: Dword = 0x0000_0010;

    // This is the complete process-access mask used by the bridge.
    const PROCESS_VM_READ: Dword = 0x0000_0010;
    const PROCESS_QUERY_LIMITED_INFORMATION: Dword = 0x0000_1000;
    const FAREVER_READ_ACCESS: Dword = PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ;

    const SUPPORTED_PROFILE_NAME: &str = "farever-2026-07-20";
    const SUPPORTED_MACHINE: u16 = 0x8664;
    const SUPPORTED_PE_TIMESTAMP: u32 = 1_784_543_904;
    const SUPPORTED_IMAGE_SIZE: u32 = 323_584;
    const SUPPORTED_FILE_SIZE: u64 = 289_792;
    const SUPPORTED_CRC32: u32 = 0x2ec4_ddc3;
    const SUPPORTED_HLBOOT_VERSION: u8 = 4;
    const SUPPORTED_HLBOOT_FILE_SIZE: u64 = 13_948_223;
    const SUPPORTED_HLBOOT_CRC32: u32 = 0xcf71_3912;
    const SUPPORTED_MAIN_CONTEXT_POINTER_RVA: usize = 0x229c8;
    const SUPPORTED_TYPE_COUNT: u32 = 45_843;
    const SUPPORTED_GLOBAL_COUNT: u32 = 30_206;
    const SUPPORTED_FUNCTION_COUNT: u32 = 47_342;
    const SUPPORTED_ENTRYPOINT: u32 = 47_939;
    const PLAYER_TYPE_INDEX: usize = 1_358;
    const HERO_TYPE_INDEX: usize = 1_366;
    /// ent.Hero.player — flattened index (st.Player owning this hero).
    /// BaseState(17)+State(10)+Entity(39)+GameObject(17)+Unit(82) = 165.
    const HERO_PLAYER_FIELD_INDEX: usize = 165;
    /// ent.Hero.loadout — flattened index (player+1, specialization+1).
    const HERO_LOADOUT_FIELD_INDEX: usize = 167;
    /// ent.Hero.name — flattened index (display name on the hero object).
    const HERO_NAME_FIELD_INDEX: usize = 173;
    const LOADOUT_TYPE_INDEX: usize = 1_369;
    /// st.Loadout.currencies — BaseState(17) + declared currencies=7 → 24.
    const LOADOUT_CURRENCIES_FIELD_INDEX: usize = 24;
    const GROUP_TYPE_INDEX: usize = 1_418;
    const PLAYER_GLOBAL_INDEX: usize = 889;
    const HERO_GLOBAL_INDEX: usize = 380;
    const GROUP_GLOBAL_INDEX: usize = 271;
    const PLAYER_STATIC_TYPE_INDEX: usize = 2_772;
    const HERO_STATIC_TYPE_INDEX: usize = 1_884;
    const GROUP_STATIC_TYPE_INDEX: usize = 1_638;
    const APP_STATIC_TYPE_INDEX: usize = 2_895;
    const APP_STATIC_GLOBAL_INDEX: usize = 955;
    const APP_INSTANCE_FIELD_INDEX: usize = 5;
    const GAME_APP_TYPE_INDEX: usize = 1_315;
    const GAME_APP_PLAYER_FIELD_INDEX: usize = 24;
    const GAME_APP_HERO_FIELD_INDEX: usize = 25;
    const GAME_APP_GUI_FIELD_INDEX: usize = 19;
    /// GameApp.camera / gameCamera — flattened indexes on GameApp (1315).
    const GAME_APP_CAMERA_FIELD_INDEX: usize = 20;
    const GAME_APP_GAME_CAMERA_FIELD_INDEX: usize = 21;
    const BASE_CAMERA_TYPE_INDEX: usize = 1_442;
    const GAME_CAMERA_TYPE_INDEX: usize = 1_443;
    const MATRIX_IMPL_TYPE_INDEX: usize = 484;
    /// Prefer live HashLink field offsets; meter byte offsets differ by build.
    /// h3d.scene.Object absPos → MatrixImpl translation (_41/_42) for world eye.
    const BASE_CAMERA_ABS_POS_FIELD_INDEX: usize = 12;
    const MATRIX_TX_FIELD_INDEX: usize = 12;
    const MATRIX_TY_FIELD_INDEX: usize = 13;
    const BASE_CAMERA_CUR_DIRECTION_FIELD_INDEX: usize = 32;
    const BASE_CAMERA_DIRECTION_FIELD_INDEX: usize = 26;
    const HERO_POS_X_FIELD_INDEX: usize = 27;
    const HERO_POS_Y_FIELD_INDEX: usize = 28;
    const HERO_POS_Z_FIELD_INDEX: usize = 29;
    const HERO_ROTATION_Z_FIELD_INDEX: usize = 30;
    // Flattened runtime field index on ent.Hero / ent.Foe (includes BaseState +
    // State + Entity + Unit). st.State.layer is 17 — not BaseState slot 14.
    const HERO_LAYER_FIELD_INDEX: usize = 17;
    const GAME_LAYER_TYPE_INDEX: usize = 782;
    // GameLayer inherits BaseState(17) + State(10) = 27 fields. Declared indexes
    // below are already flattened (declared + 27), matching units=20+27.
    // getMapId (fn 7274) reads world@32 then World.level@23.
    const GAME_LAYER_WORLD_FIELD_INDEX: usize = 32;
    const GAME_LAYER_MAIN_ACTIVITY_FIELD_INDEX: usize = 35;
    const GAME_LAYER_IS_RIFT_FIELD_INDEX: usize = 36;
    // st.GameLayer.units is 47. entities (44) is the wider net; meter sweeps
    // both for heroes (deduped). interactibles is 46.
    const GAME_LAYER_ENTITIES_FIELD_INDEX: usize = 44;
    const GAME_LAYER_INTERACTIBLES_FIELD_INDEX: usize = 46;
    const GAME_LAYER_UNITS_FIELD_INDEX: usize = 47;
    const WORLD_TYPE_INDEX: usize = 787;
    // world.World inherits h3d.scene.Object (20 fields).
    const WORLD_LEVEL_FIELD_INDEX: usize = 23;
    // world.World.timeOfDay — day-cycle controller (world.TimeOfDay).
    const WORLD_TIME_OF_DAY_FIELD_INDEX: usize = 31;
    const WORLD_IS_WORLD_MAP_FIELD_INDEX: usize = 45;
    const TIME_OF_DAY_TYPE_INDEX: usize = 881;
    // world.TimeOfDay has no inherited fields; declared indexes match runtime.
    const TIME_OF_DAY_SPEED_FIELD_INDEX: usize = 1;
    const TIME_OF_DAY_PAUSED_FIELD_INDEX: usize = 2;
    const TIME_OF_DAY_ELAPSED_FIELD_INDEX: usize = 3;
    const TIME_OF_DAY_PREV_FACTOR_FIELD_INDEX: usize = 4;
    const ACTIVITY_TYPE_INDEX: usize = 1_590;
    // st.activity.DungeonBase (5094) / Dungeon (5095) — object_is_a walks supers.
    const ACTIVITY_DUNGEON_BASE_TYPE_INDEX: usize = 5_094;
    // st.Activity inherits Entity+State+BaseState (66 fields); kind is declared 0.
    const ACTIVITY_KIND_FIELD_INDEX: usize = 66;
    const FOE_TYPE_INDEX: usize = 1_381;
    // Live gatherable / chest markers (GameLayer.interactibles).
    const GATHERABLE_TYPE_INDEX: usize = 5_898;
    const CHEST_TYPE_INDEX: usize = 5_096;
    // ent.Element.kind (String) — flattened index on Gatherable / Chest.
    const ELEMENT_KIND_FIELD_INDEX: usize = 86;
    const INTERACTIBLE_ENABLED_FIELD_INDEX: usize = 83;
    const INTERACTIBLE_SWEEP_RADIUS: f64 = 500.0;
    const INTERACTIBLE_SWEEP_Z_CULL: f64 = 160.0;
    const INTERACTIBLE_SWEEP_MAX: usize = 200;
    const STATE_TYPE_INDEX: usize = 781;
    const STATE_REMOVED_FIELD_INDEX: usize = 0;
    // ent.Foe.summonOwner is 167. Index 164 is ent.Unit.lastObjOffset, which is
    // almost always non-zero and incorrectly filters every live foe as a summon.
    const FOE_SUMMON_OWNER_FIELD_INDEX: usize = 167;
    // Nearby-enemy map sweep (GameLayer.units / ent.Foe). Independent of DPS.
    // Radius/z caps tuned from FareverMeter world-sweep bounds (500 m / 2× Z).
    const ENEMY_SWEEP_RADIUS: f64 = 500.0;
    const ENEMY_SWEEP_Z_CULL: f64 = 120.0;
    const ENEMY_SWEEP_MAX: usize = 150;
    // Layer roster of non-party players (GameLayer.units + entities / ent.Hero).
    // No range cull — distance is display-only — matching FareverMeter's
    // uncapped hero sweep (SWEEP_MAX=400, array length bound 20000).
    const PLAYER_SWEEP_MAX: usize = 400;
    const PLAYER_ARRAY_LENGTH_MAX: i32 = 20_000;
    // Runtime field indexes include inherited fields. These indexes are
    // derived from the supported hlboot.dat metadata, never guessed offsets.
    const PLAYER_NAME_FIELD_INDEX: usize = 29;
    const PLAYER_UID_FIELD_INDEX: usize = 28;
    const PLAYER_GROUP_FIELD_INDEX: usize = 37;
    // st.Player inherits BaseState(17)+State(10)=27. Declared: accountProgress=6,
    // heroData=7, progress=8, stats=9, group=10 → flattened 33..37.
    const PLAYER_PROGRESS_FIELD_INDEX: usize = 35;
    const PLAYER_HERO_DATA_FIELD_INDEX: usize = 34;
    const PLAYER_HERO_FIELD_INDEX: usize = 43;
    const PLAYER_CONNECTED_FIELD_INDEX: usize = 30;
    const UNIT_ATTRIBUTES_FIELD_INDEX: usize = 133;
    const UNIT_LEVEL_FIELD_INDEX: usize = 134;
    const UNIT_IN_COMBAT_FIELD_INDEX: usize = 94;
    const UNIT_KIND_FIELD_INDEX: usize = 83;
    const UNIT_ATTRIBUTES_TYPE_INDEX: usize = 1_104;
    const HERO_ATTRIBUTES_TYPE_INDEX: usize = 6_568;
    const INT_MAP_TYPE_INDEX: usize = 140;
    const INT_MAP_HANDLE_FIELD_INDEX: usize = 0;
    const ATTR_VITALITY_FIELD_INDEX: usize = 5;
    const ATTR_HEALTH_FIELD_INDEX: usize = 29;
    const ATTR_LAST_RESOURCE_MAX_FIELD_INDEX: usize = 2;
    const ATTR_MAX_HEALTH_FIELD_INDEX: usize = 30;
    const ATTR_HEALTH_REGEN_FIELD_INDEX: usize = 31;
    const ATTR_SHIELD_FIELD_INDEX: usize = 32;
    const ATTR_SPECIAL_ENERGY_FIELD_INDEX: usize = 33;
    const ATTR_SPECIAL_ENERGY_REGEN_FIELD_INDEX: usize = 34;
    const GAME_UI_TYPE_INDEX: usize = 1_326;
    const GAME_UI_GAME_ROOT_FIELD_INDEX: usize = 33;
    const GAME_UI_ROOT_TYPE_INDEX: usize = 1_327;
    const GAME_UI_ROOT_HUD_FIELD_INDEX: usize = 163;
    const BASE_UI_WIDGETS_FIELD_INDEX: usize = 22;
    const WIDGET_CONTAINER_FIELD_INDEX: usize = 177;
    const H2D_OBJECT_TYPE_INDEX: usize = 260;
    const H2D_OBJECT_CHILDREN_FIELD_INDEX: usize = 0;
    const H2D_OBJECT_PARENT_FIELD_INDEX: usize = 2;
    const H2D_OBJECT_VISIBLE_FIELD_INDEX: usize = 9;
    const ARRAY_OBJ_TYPE_INDEX: usize = 47;
    const ARRAY_PROXY_TYPE_INDEX: usize = 977;
    const ARRAY_PROXY_ARRAY_FIELD_INDEX: usize = 4;
    const ARRAY_DYN_TYPE_INDEX: usize = 266;
    const ARRAY_DYN_ARRAY_FIELD_INDEX: usize = 0;
    const GROUP_PLAYERS_FIELD_INDEX: usize = 28;
    const PROGRESS_TYPE_INDEX: usize = 1_415;
    // st.player.Progress inherits BaseState(17); counters is declared field 2 → 19.
    const PROGRESS_COUNTERS_FIELD_INDEX: usize = 19;
    const PROGRESS_ELEMENTS_FIELD_INDEX: usize = 21;
    const MAP_DATA_TYPE_INDEX: usize = 1_038;
    const MAP_DATA_MAP_FIELD_INDEX: usize = 4;
    const STRING_MAP_TYPE_INDEX: usize = 66;
    const STRING_MAP_HANDLE_FIELD_INDEX: usize = 0;
    const COMPLETION_PROXY_TYPE_INDEX: usize = 23_065;
    const COMPLETION_PROXY_COMPLETED_FIELD_INDEX: usize = 2;
    const HERO_DATA_TYPE_INDEX: usize = 1_365;
    // Flattened indexes: BaseState(17)+DBState(4)=21 inherited, then HeroData
    // declared fields (currencies=17 → 38, progress=23 → 44).
    const HERO_DATA_CURRENCIES_FIELD_INDEX: usize = 38;
    const HERO_DATA_PROGRESS_FIELD_INDEX: usize = 44;
    const HL_TYPE_KIND_I32: u32 = 3;
    const HL_TYPE_KIND_F64: u32 = 6;
    const HL_TYPE_KIND_OBJ: u32 = 11;
    const HL_TYPE_KIND_VIRTUAL: u32 = 15;
    const HL_VTYPE_FIELDS_OFFSET: usize = 0x00;
    const HL_VTYPE_NFIELDS_OFFSET: usize = 0x08;
    const HL_VFIELD_STRIDE: usize = 24;
    const HL_VFIELD_NAME_OFFSET: usize = 0x00;
    const HL_VFIELD_TYPE_OFFSET: usize = 0x08;
    const HL_VVIRTUAL_DATA_OFFSET: usize = 24;
    const ARRAY_LENGTH_FIELD_INDEX: usize = 0;
    const ARRAY_STORAGE_FIELD_INDEX: usize = 1;
    const HERO_WIDGET_TYPE_INDEX: usize = 19_256;
    const HERO_WIDGET_HERO_FIELD_INDEX: usize = 165;
    const HERO_WIDGET_HEALTH_BAR_FIELD_INDEX: usize = 167;
    const HEALTH_BAR_TYPE_INDEX: usize = 18_926;
    const HEALTH_BAR_HEALTH_GAUGE_FIELD_INDEX: usize = 163;
    const HEALTH_BAR_SHIELD_GAUGE_FIELD_INDEX: usize = 164;
    const ATTRIBUTE_BAR_TYPE_INDEX: usize = 15_721;
    const ATTRIBUTE_BAR_UNIT_FIELD_INDEX: usize = 196;
    const ATTRIBUTE_BAR_ID_FIELD_INDEX: usize = 197;
    const BASE_GAUGE_MAX_FIELD_INDEX: usize = 177;
    const BASE_GAUGE_VALUE_FIELD_INDEX: usize = 175;

    #[repr(C)]
    struct ProcessEntry32W {
        dw_size: Dword,
        cnt_usage: Dword,
        process_id: Dword,
        default_heap_id: UlongPtr,
        module_id: Dword,
        threads: Dword,
        parent_process_id: Dword,
        priority_class_base: Long,
        flags: Dword,
        exe_file: [u16; MAX_PATH],
    }

    #[repr(C)]
    struct ModuleEntry32W {
        dw_size: Dword,
        module_id: Dword,
        process_id: Dword,
        global_usage: Dword,
        process_usage: Dword,
        base_address: *mut u8,
        base_size: Dword,
        module: Handle,
        module_name: [u16; MAX_MODULE_NAME32 + 1],
        exe_path: [u16; MAX_PATH],
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CloseHandle(object: Handle) -> Bool;
        fn CreateToolhelp32Snapshot(flags: Dword, process_id: Dword) -> Handle;
        fn GetLastError() -> Dword;
        fn Module32FirstW(snapshot: Handle, entry: *mut ModuleEntry32W) -> Bool;
        fn Module32NextW(snapshot: Handle, entry: *mut ModuleEntry32W) -> Bool;
        fn OpenProcess(access: Dword, inherit_handle: Bool, process_id: Dword) -> Handle;
        fn Process32FirstW(snapshot: Handle, entry: *mut ProcessEntry32W) -> Bool;
        fn Process32NextW(snapshot: Handle, entry: *mut ProcessEntry32W) -> Bool;
        fn ReadProcessMemory(
            process: Handle,
            base_address: *const c_void,
            buffer: *mut c_void,
            size: usize,
            bytes_read: *mut usize,
        ) -> Bool;
    }

    struct OwnedHandle(NonNull<c_void>);

    impl OwnedHandle {
        fn new(handle: Handle) -> Option<Self> {
            if handle.is_null() || handle == INVALID_HANDLE_VALUE {
                None
            } else {
                NonNull::new(handle).map(Self)
            }
        }

        fn raw(&self) -> Handle {
            self.0.as_ptr()
        }
    }

    impl Drop for OwnedHandle {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.raw());
            }
        }
    }

    fn last_error() -> Dword {
        unsafe { GetLastError() }
    }

    fn read_process_bytes(
        process: &OwnedHandle,
        address: usize,
        size: usize,
    ) -> Result<Vec<u8>, String> {
        let buffer = read_process_bytes_partial(process, address, size)?;
        if buffer.len() != size {
            return Err(format!(
                "read-only process read at 0x{address:x} failed: requested {size}, read {} (partial)",
                buffer.len()
            ));
        }
        Ok(buffer)
    }

    /// Like `read_process_bytes`, but accepts a short read (Wine/Windows
    /// ERROR_PARTIAL_COPY near page edges). Callers must handle truncation.
    fn read_process_bytes_partial(
        process: &OwnedHandle,
        address: usize,
        size: usize,
    ) -> Result<Vec<u8>, String> {
        if size == 0 || size > 4096 {
            return Err(format!("refusing invalid process read size {size}"));
        }
        let mut buffer = vec![0_u8; size];
        let mut bytes_read = 0_usize;
        let succeeded = unsafe {
            ReadProcessMemory(
                process.raw(),
                address as *const c_void,
                buffer.as_mut_ptr().cast(),
                size,
                &mut bytes_read,
            )
        };
        if bytes_read == 0 {
            return Err(format!(
                "read-only process read at 0x{address:x} failed: requested {size}, read 0 (Win32 error {})",
                last_error()
            ));
        }
        if succeeded == FALSE && bytes_read < size {
            // ERROR_PARTIAL_COPY (299) and similar: keep the readable prefix.
            buffer.truncate(bytes_read);
            return Ok(buffer);
        }
        if succeeded == FALSE {
            return Err(format!(
                "read-only process read at 0x{address:x} failed: requested {size}, read {bytes_read} (Win32 error {})",
                last_error()
            ));
        }
        buffer.truncate(bytes_read);
        Ok(buffer)
    }

    fn decode_utf16_z(bytes: &[u8], label: &str) -> Result<Option<String>, String> {
        let mut units = Vec::with_capacity(bytes.len() / 2);
        for pair in bytes.chunks_exact(2) {
            let unit = u16::from_le_bytes([pair[0], pair[1]]);
            if unit == 0 {
                let value = String::from_utf16(&units)
                    .map_err(|_| format!("{label} is not valid UTF-16"))?;
                return Ok(Some(value));
            }
            units.push(unit);
        }
        Ok(None)
    }

    fn verify_live_pe_header(process: &OwnedHandle, module: &ModuleInfo) -> Result<(), String> {
        let dos_header = read_process_bytes(process, module.base_address, 64)?;
        if dos_header.get(0..2) != Some(b"MZ") {
            return Err(format!(
                "{} live image has an invalid DOS header",
                module.name
            ));
        }
        let pe_offset = read_u32_le(&dos_header, 0x3c)? as usize;
        if pe_offset > module.size as usize || pe_offset + 4 > module.size as usize {
            return Err(format!(
                "{} live PE header offset is outside its module",
                module.name
            ));
        }
        let pe_signature = read_process_bytes(process, module.base_address + pe_offset, 4)?;
        if pe_signature != b"PE\0\0" {
            return Err(format!(
                "{} live image has an invalid PE signature",
                module.name
            ));
        }
        Ok(())
    }

    struct RuntimeAnchor {
        pointer_address: usize,
        context_address: usize,
        file_address: usize,
        code_address: usize,
        module_address: usize,
    }

    struct CodeAnchor {
        types_address: usize,
        globals_address: usize,
        player: GlobalAnchor,
        hero: GlobalAnchor,
        group: GlobalAnchor,
        player_root: PlayerRoot,
    }

    struct GlobalAnchor {
        type_address: usize,
        object_metadata_address: usize,
        slot_address: usize,
        value_address: usize,
        value_type_address: usize,
    }

    struct PlayerRoot {
        app_static_holder_address: usize,
        game_app_address: usize,
        player_address: usize,
        hero_address: usize,
        position_x: f64,
        position_y: f64,
        position_z: f64,
        rotation_z: f64,
        app_instance_offset: usize,
        player_offset: usize,
        hero_offset: usize,
        gui_offset: usize,
        game_camera_offset: usize,
        camera_offset: usize,
        camera_abs_pos_offset: usize,
        matrix_tx_offset: usize,
        matrix_ty_offset: usize,
        camera_cur_direction_offset: usize,
        camera_direction_offset: usize,
        position_x_offset: usize,
        position_y_offset: usize,
        position_z_offset: usize,
        rotation_z_offset: usize,
        layer_offset: usize,
        game_layer_world_offset: usize,
        game_layer_main_activity_offset: usize,
        game_layer_is_rift_offset: usize,
        game_layer_interactibles_offset: usize,
        game_layer_entities_offset: usize,
        game_layer_units_offset: usize,
        world_level_offset: usize,
        world_time_of_day_offset: usize,
        world_is_world_map_offset: usize,
        time_of_day_speed_offset: usize,
        time_of_day_paused_offset: usize,
        time_of_day_elapsed_offset: usize,
        time_of_day_prev_factor_offset: usize,
        activity_kind_offset: usize,
        state_removed_offset: usize,
        interactible_enabled_offset: usize,
        element_kind_offset: usize,
        foe_summon_owner_offset: usize,
        player_name_offset: usize,
        player_uid_offset: usize,
        hero_player_offset: usize,
        hero_name_offset: usize,
        player_group_offset: usize,
        player_progress_offset: usize,
        player_hero_data_offset: usize,
        player_hero_offset: usize,
        player_connected_offset: usize,
        attributes_offset: usize,
        level_offset: usize,
        in_combat_offset: usize,
        unit_kind_offset: usize,
        vitality_offset: usize,
        health_offset: usize,
        last_resource_max_offset: usize,
        int_map_handle_offset: usize,
        max_health_offset: usize,
        health_regen_offset: usize,
        shield_offset: usize,
        special_energy_offset: usize,
        special_energy_regen_offset: usize,
        widgets_offset: usize,
        game_ui_game_root_offset: usize,
        game_ui_root_hud_offset: usize,
        widget_container_offset: usize,
        h2d_children_offset: usize,
        h2d_parent_offset: usize,
        h2d_visible_offset: usize,
        array_length_offset: usize,
        array_storage_offset: usize,
        array_proxy_array_offset: usize,
        array_dyn_array_offset: usize,
        group_players_offset: usize,
        progress_counters_offset: usize,
        progress_elements_offset: usize,
        map_data_map_offset: usize,
        string_map_handle_offset: usize,
        completion_proxy_completed_offset: usize,
        hero_data_currencies_offset: usize,
        hero_data_progress_offset: usize,
        hero_loadout_offset: usize,
        loadout_currencies_offset: usize,
        hero_widget_hero_offset: usize,
        hero_widget_health_bar_offset: usize,
        health_bar_health_gauge_offset: usize,
        health_bar_shield_gauge_offset: usize,
        base_gauge_max_offset: usize,
        base_gauge_value_offset: usize,
        attribute_bar_unit_offset: usize,
        attribute_bar_id_offset: usize,
    }

    #[derive(Clone, Copy)]
    struct FoeHealth {
        address: usize,
        health: f64,
    }

    struct EnemySample {
        address: usize,
        kind: String,
        x: f64,
        y: f64,
        z: f64,
    }

    /// Live heroes on the current GameLayer that are not the local player and
    /// not in the party. Distance is for UI sort/display only.
    struct LayerPlayerSample {
        address: usize,
        name: String,
        uid: String,
        class_name: String,
        level: i32,
        x: f64,
        y: f64,
        z: f64,
        rotation: f64,
        distance: f64,
    }

    struct InteractibleSample {
        address: usize,
        /// Atlas loot category: ore | plant | chest | gatherable
        category: &'static str,
        /// Element.kind / display name (e.g. Ore_Copper_Small).
        name: String,
        x: f64,
        y: f64,
        z: f64,
    }

    struct ObservedDps {
        previous: HashMap<usize, f64>,
        total: f64,
        fight_id: u64,
        started: Option<Instant>,
        last_damage: Option<Instant>,
        active: bool,
    }

    impl ObservedDps {
        fn new() -> Self {
            Self {
                previous: HashMap::new(),
                total: 0.0,
                fight_id: 0,
                started: None,
                last_damage: None,
                active: false,
            }
        }

        fn update(&mut self, foes: &[FoeHealth], player_in_combat: bool, now: Instant) {
            let mut damage = 0.0;
            let mut current = HashMap::with_capacity(foes.len());
            for foe in foes {
                if let Some(previous) = self.previous.get(&foe.address) {
                    let loss = *previous - foe.health;
                    if loss.is_finite() && loss > 0.0 && loss <= 1_000_000_000.0 {
                        damage += loss;
                    }
                }
                current.insert(foe.address, foe.health);
            }
            self.previous = current;

            // Only extend the observed fight while the local player is in combat.
            // Nearby damage from other players must not keep dps.in_combat stuck true
            // after the hero has left combat (that also stuck the Atlas combat icon).
            if player_in_combat && damage > 0.0 {
                if !self.active {
                    self.active = true;
                    self.total = 0.0;
                    self.fight_id = self.fight_id.wrapping_add(1);
                    self.started = Some(now);
                }
                self.total += damage;
                self.last_damage = Some(now);
            } else if self.active
                && !player_in_combat
                && self
                    .last_damage
                    .is_some_and(|last| now.duration_since(last) >= Duration::from_secs(3))
            {
                self.active = false;
            }
        }

        fn elapsed(&self, now: Instant) -> f64 {
            self.started
                .map(|started| now.duration_since(started).as_secs_f64())
                .unwrap_or(0.0)
        }
    }

    fn read_runtime_anchor(
        process: &OwnedHandle,
        farever_module: &ModuleInfo,
    ) -> Result<RuntimeAnchor, String> {
        let pointer_address = farever_module
            .base_address
            .checked_add(SUPPORTED_MAIN_CONTEXT_POINTER_RVA)
            .ok_or_else(|| "main-context pointer address overflowed".to_owned())?;
        let pointer_bytes = read_process_bytes(process, pointer_address, 8)?;
        let context_address = read_u64_le(&pointer_bytes, 0)? as usize;
        if context_address == 0 {
            return Err("HashLink main context is not initialized".to_owned());
        }

        // main_context: file, code, module, return value, file timestamp.
        let context = read_process_bytes(process, context_address, 40)?;
        let file_address = read_u64_le(&context, 0)? as usize;
        let code_address = read_u64_le(&context, 8)? as usize;
        let module_address = read_u64_le(&context, 16)? as usize;
        if file_address == 0 || code_address == 0 || module_address == 0 {
            return Err("HashLink main context contains a null required pointer".to_owned());
        }

        let file_name_bytes = read_process_bytes(process, file_address, 22)?;
        let file_name = file_name_bytes
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect::<Vec<_>>();
        if wide_string(&file_name) != "hlboot.dat" {
            return Err("HashLink main context does not reference hlboot.dat".to_owned());
        }

        let module_code = read_process_bytes(process, module_address, 8)?;
        if read_u64_le(&module_code, 0)? as usize != code_address {
            return Err("HashLink module/code pointer cross-check failed".to_owned());
        }

        Ok(RuntimeAnchor {
            pointer_address,
            context_address,
            file_address,
            code_address,
            module_address,
        })
    }

    fn read_code_anchor(
        process: &OwnedHandle,
        runtime: &RuntimeAnchor,
        require_live_player: bool,
    ) -> Result<CodeAnchor, String> {
        // HashLink hl_code through its constants pointer. This is metadata, not
        // the globals' values or any GC-managed game object.
        let code = read_process_bytes(process, runtime.code_address, 168)?;
        let version = read_u32_le(&code, 0)?;
        let type_count = read_u32_le(&code, 20)?;
        let global_count = read_u32_le(&code, 24)?;
        let function_count = read_u32_le(&code, 32)?;
        let entrypoint = read_u32_le(&code, 40)?;
        if version != SUPPORTED_HLBOOT_VERSION as u32
            || type_count != SUPPORTED_TYPE_COUNT
            || global_count != SUPPORTED_GLOBAL_COUNT
            || function_count != SUPPORTED_FUNCTION_COUNT
            || entrypoint != SUPPORTED_ENTRYPOINT
        {
            return Err(format!(
                "live HashLink code header mismatch: version={version}, types={type_count}, globals={global_count}, functions={function_count}, entrypoint={entrypoint}"
            ));
        }

        let types_address = read_u64_le(&code, 128)? as usize;
        let globals_address = read_u64_le(&code, 136)? as usize;
        if types_address == 0 || globals_address == 0 {
            return Err("live HashLink code has a null type/global table".to_owned());
        }

        let module_header = read_process_bytes(process, runtime.module_address, 32)?;
        let globals_indexes_address = read_u64_le(&module_header, 16)? as usize;
        let globals_data_address = read_u64_le(&module_header, 24)? as usize;
        if globals_indexes_address == 0 || globals_data_address == 0 {
            return Err("live HashLink module has a null globals table".to_owned());
        }

        let player = read_global_anchor(
            process,
            types_address,
            globals_indexes_address,
            globals_data_address,
            PLAYER_TYPE_INDEX,
            PLAYER_GLOBAL_INDEX,
            "st.Player",
            PLAYER_STATIC_TYPE_INDEX,
            "st.$Player",
        )?;
        let hero = read_global_anchor(
            process,
            types_address,
            globals_indexes_address,
            globals_data_address,
            HERO_TYPE_INDEX,
            HERO_GLOBAL_INDEX,
            "ent.Hero",
            HERO_STATIC_TYPE_INDEX,
            "ent.$Hero",
        )?;
        let group = read_global_anchor(
            process,
            types_address,
            globals_indexes_address,
            globals_data_address,
            GROUP_TYPE_INDEX,
            GROUP_GLOBAL_INDEX,
            "st.Group",
            GROUP_STATIC_TYPE_INDEX,
            "st.$Group",
        )?;
        let player_root = read_player_root(
            process,
            types_address,
            globals_address,
            globals_indexes_address,
            globals_data_address,
            require_live_player,
        )?;

        Ok(CodeAnchor {
            types_address,
            globals_address,
            player,
            hero,
            group,
            player_root,
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn read_global_anchor(
        process: &OwnedHandle,
        types_address: usize,
        globals_indexes_address: usize,
        globals_data_address: usize,
        type_index: usize,
        global_index: usize,
        expected_name: &str,
        value_type_index: usize,
        expected_value_type_name: &str,
    ) -> Result<GlobalAnchor, String> {
        let type_address = types_address
            .checked_add(type_index * 32)
            .ok_or_else(|| format!("{expected_name} type address overflowed"))?;
        let live_type = read_process_bytes(process, type_address, 16)?;
        if read_u32_le(&live_type, 0)? != 11 {
            return Err(format!("{expected_name} is not a HashLink object type"));
        }
        let object_metadata_address = read_u64_le(&live_type, 8)? as usize;
        let object_metadata = read_process_bytes(process, object_metadata_address, 64)?;
        let name_address = read_u64_le(&object_metadata, 16)? as usize;
        let name_size = (expected_name.encode_utf16().count() + 1) * 2;
        let name_bytes = read_process_bytes(process, name_address, name_size)?;
        let name = name_bytes
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect::<Vec<_>>();
        if wide_string(&name) != expected_name {
            return Err(format!(
                "live type {type_index} is not named {expected_name}"
            ));
        }

        let metadata_slot_address = read_u64_le(&object_metadata, 56)? as usize;
        let resolved_global_index = global_index
            .checked_sub(1)
            .ok_or_else(|| format!("{expected_name} has an invalid zero global reference"))?;
        let index_address = globals_indexes_address
            .checked_add(resolved_global_index * 4)
            .ok_or_else(|| format!("{expected_name} global index address overflowed"))?;
        let index_bytes = read_process_bytes(process, index_address, 4)?;
        let global_offset = i32::from_le_bytes(index_bytes.try_into().unwrap());
        if global_offset < 0 {
            return Err(format!("{expected_name} has an invalid global offset"));
        }
        let slot_address = globals_data_address
            .checked_add(global_offset as usize)
            .ok_or_else(|| format!("{expected_name} global slot address overflowed"))?;
        if slot_address != metadata_slot_address {
            return Err(format!(
                "{expected_name} global slot cross-check failed: index entry={global_offset}, globals_data=0x{globals_data_address:x}, computed=0x{slot_address:x}, metadata=0x{metadata_slot_address:x}"
            ));
        }
        let value_address =
            read_u64_le(&read_process_bytes(process, slot_address, 8)?, 0)? as usize;
        if value_address == 0 {
            return Err(format!("{expected_name} global value is not populated"));
        }
        let value_type_address =
            read_u64_le(&read_process_bytes(process, value_address, 8)?, 0)? as usize;
        let expected_value_type_address = types_address
            .checked_add(value_type_index * 32)
            .ok_or_else(|| format!("{expected_value_type_name} type address overflowed"))?;
        if value_type_address != expected_value_type_address {
            return Err(format!(
                "{expected_name} global object type mismatch: expected {expected_value_type_name}=0x{expected_value_type_address:x}, actual=0x{value_type_address:x}"
            ));
        }
        let value_type = read_process_bytes(process, value_type_address, 16)?;
        if read_u32_le(&value_type, 0)? != 11 {
            return Err(format!("{expected_value_type_name} is not an object type"));
        }
        let value_type_metadata = read_u64_le(&value_type, 8)? as usize;
        let value_type_object = read_process_bytes(process, value_type_metadata, 24)?;
        let value_type_name_address = read_u64_le(&value_type_object, 16)? as usize;
        let value_type_name_size = (expected_value_type_name.encode_utf16().count() + 1) * 2;
        let value_type_name_bytes =
            read_process_bytes(process, value_type_name_address, value_type_name_size)?;
        let value_type_name = value_type_name_bytes
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect::<Vec<_>>();
        if wide_string(&value_type_name) != expected_value_type_name {
            return Err(format!(
                "live type {value_type_index} is not named {expected_value_type_name}"
            ));
        }

        Ok(GlobalAnchor {
            type_address,
            object_metadata_address,
            slot_address,
            value_address,
            value_type_address,
        })
    }

    fn object_field_offset(
        process: &OwnedHandle,
        type_address: usize,
        field_index: usize,
    ) -> Result<usize, String> {
        let live_type = read_process_bytes(process, type_address, 16)?;
        let object_metadata_address = read_u64_le(&live_type, 8)? as usize;
        let object_metadata = read_process_bytes(process, object_metadata_address, 80)?;
        let runtime_object_address = read_u64_le(&object_metadata, 72)? as usize;
        if runtime_object_address == 0 {
            return Err("HashLink runtime object metadata is not initialized".to_owned());
        }
        let runtime_object = read_process_bytes(process, runtime_object_address, 48)?;
        let field_offsets_address = read_u64_le(&runtime_object, 40)? as usize;
        let field_offset_address = field_offsets_address
            .checked_add(field_index * 4)
            .ok_or_else(|| "HashLink field-offset address overflowed".to_owned())?;
        let field_offset =
            read_u32_le(&read_process_bytes(process, field_offset_address, 4)?, 0)? as usize;
        Ok(field_offset)
    }

    fn read_object_pointer_field(
        process: &OwnedHandle,
        object_address: usize,
        field_offset: usize,
    ) -> Result<usize, String> {
        let address = object_address
            .checked_add(field_offset)
            .ok_or_else(|| "HashLink object field address overflowed".to_owned())?;
        Ok(read_u64_le(&read_process_bytes(process, address, 8)?, 0)? as usize)
    }

    fn object_is_a(
        process: &OwnedHandle,
        object_address: usize,
        expected_type_address: usize,
    ) -> bool {
        let Ok(bytes) = read_process_bytes(process, object_address, 8) else {
            return false;
        };
        let Ok(mut current_type) = read_u64_le(&bytes, 0).map(|value| value as usize) else {
            return false;
        };
        for _ in 0..32 {
            if current_type == expected_type_address {
                return true;
            }
            let Ok(type_bytes) = read_process_bytes(process, current_type, 16) else {
                return false;
            };
            if read_u32_le(&type_bytes, 0).ok() != Some(11) {
                return false;
            }
            let Ok(metadata) = read_u64_le(&type_bytes, 8).map(|value| value as usize) else {
                return false;
            };
            let Ok(super_bytes) = read_process_bytes(process, metadata + 0x18, 8) else {
                return false;
            };
            let Ok(parent) = read_u64_le(&super_bytes, 0).map(|value| value as usize) else {
                return false;
            };
            if parent == 0 || parent == current_type {
                return false;
            }
            current_type = parent;
        }
        false
    }

    fn read_live_foe_health(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hero: usize,
    ) -> Result<Vec<FoeHealth>, String> {
        let root = &code.player_root;
        let layer = read_object_pointer_field(process, hero, root.layer_offset)?;
        if layer == 0
            || read_u64_le(&read_process_bytes(process, layer, 8)?, 0)? as usize
                != code.types_address + GAME_LAYER_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let units = read_object_pointer_field(process, layer, root.game_layer_units_offset)?;
        if units == 0
            || read_u64_le(&read_process_bytes(process, units, 8)?, 0)? as usize
                != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let length = i32::from_le_bytes(
            read_process_bytes(process, units + root.array_length_offset, 4)?
                .try_into()
                .unwrap(),
        );
        if !(0..=2_000).contains(&length) {
            return Err("GameLayer.units has an invalid length".to_owned());
        }
        let storage = read_object_pointer_field(process, units, root.array_storage_offset)?;
        if storage == 0 {
            return Ok(Vec::new());
        }
        let foe_type = code.types_address + FOE_TYPE_INDEX * 32;
        let mut foes = Vec::new();
        for index in 0..length as usize {
            let entry = storage
                .checked_add(24 + index * 8)
                .ok_or_else(|| "GameLayer.units entry address overflowed".to_owned())?;
            let unit = read_u64_le(&read_process_bytes(process, entry, 8)?, 0)? as usize;
            if unit == 0 || !object_is_a(process, unit, foe_type) {
                continue;
            }
            if read_process_bytes(process, unit + root.state_removed_offset, 1)?[0] != 0 {
                continue;
            }
            if read_object_pointer_field(process, unit, root.foe_summon_owner_offset)? != 0 {
                continue;
            }
            let attributes = read_object_pointer_field(process, unit, root.attributes_offset)?;
            if attributes == 0 {
                continue;
            }
            let health = read_f64_le(
                &read_process_bytes(process, attributes + root.health_offset, 8)?,
                0,
            )?;
            if health.is_finite() && (0.0..=1_000_000_000.0).contains(&health) {
                foes.push(FoeHealth { address: unit, health });
            }
        }
        Ok(foes)
    }

    /// Nearby hostile units for the Atlas map.
    ///
    /// Walks `st.GameLayer.units`, keeps live `ent.Foe` objects that are not
    /// summons, and culls by horizontal radius / vertical separation. This is
    /// intentionally separate from the legacy DPS health sampler.
    fn classify_instance(
        map_id: &str,
        is_rift: bool,
        is_dungeon: bool,
        is_world_map: bool,
        activity_kind: &str,
    ) -> &'static str {
        // Rift flag first, then dungeon activity type (st.activity.DungeonBase),
        // then world map. Remaining non-world loaded maps stay "instance".
        if is_rift
            || map_id.to_ascii_lowercase().contains("rift")
            || activity_kind.to_ascii_lowercase().contains("rift")
        {
            return "rift";
        }
        let activity = activity_kind.to_ascii_lowercase();
        let map = map_id.to_ascii_lowercase();
        if is_dungeon || activity.contains("dungeon") || map.contains("dungeon") {
            return "dungeon";
        }
        if is_world_map || map_id.starts_with("World/") {
            return "world";
        }
        if !map_id.is_empty() {
            return "instance";
        }
        "unknown"
    }

    fn read_instance_context(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hero: usize,
    ) -> InstanceSample {
        let unknown = InstanceSample {
            kind: "unknown",
            map_id: String::new(),
            is_rift: false,
            is_dungeon: false,
            is_world_map: false,
            activity_kind: String::new(),
        };
        let root = &code.player_root;
        let Ok(layer) = read_object_pointer_field(process, hero, root.layer_offset) else {
            return unknown;
        };
        let Ok(layer_bytes) = read_process_bytes(process, layer, 8) else {
            return unknown;
        };
        let Ok(layer_type) = read_u64_le(&layer_bytes, 0).map(|value| value as usize) else {
            return unknown;
        };
        if layer == 0 || layer_type != code.types_address + GAME_LAYER_TYPE_INDEX * 32 {
            return unknown;
        }
        let is_rift = read_process_bytes(process, layer + root.game_layer_is_rift_offset, 1)
            .ok()
            .map(|bytes| bytes[0] != 0)
            .unwrap_or(false);

        let mut map_id = String::new();
        let mut is_world_map = false;
        if let Ok(world) = read_object_pointer_field(process, layer, root.game_layer_world_offset) {
            if world != 0
                && object_is_a(
                    process,
                    world,
                    code.types_address + WORLD_TYPE_INDEX * 32,
                )
            {
                is_world_map =
                    read_process_bytes(process, world + root.world_is_world_map_offset, 1)
                        .ok()
                        .map(|bytes| bytes[0] != 0)
                        .unwrap_or(false);
                if let Ok(level_pointer) =
                    read_object_pointer_field(process, world, root.world_level_offset)
                {
                    map_id = read_hashlink_string(
                        process,
                        code.types_address,
                        level_pointer,
                        "world level / map id",
                    )
                    .unwrap_or_default();
                }
            }
        }

        let mut activity_kind = String::new();
        let mut is_dungeon = false;
        if let Ok(activity) =
            read_object_pointer_field(process, layer, root.game_layer_main_activity_offset)
        {
            if activity != 0
                && object_is_a(
                    process,
                    activity,
                    code.types_address + ACTIVITY_TYPE_INDEX * 32,
                )
            {
                is_dungeon = object_is_a(
                    process,
                    activity,
                    code.types_address + ACTIVITY_DUNGEON_BASE_TYPE_INDEX * 32,
                );
                if let Ok(kind_pointer) =
                    read_object_pointer_field(process, activity, root.activity_kind_offset)
                {
                    activity_kind = read_hashlink_identifier(
                        process,
                        code.types_address,
                        kind_pointer,
                        "activity kind",
                    )
                    .or_else(|_| {
                        read_hashlink_string(
                            process,
                            code.types_address,
                            kind_pointer,
                            "activity kind",
                        )
                    })
                    .unwrap_or_default();
                }
            }
        }

        let kind = classify_instance(
            &map_id,
            is_rift,
            is_dungeon,
            is_world_map,
            &activity_kind,
        );
        InstanceSample {
            kind,
            map_id,
            is_rift,
            is_dungeon,
            is_world_map,
            activity_kind,
        }
    }

    fn read_time_of_day(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hero: usize,
    ) -> Option<TimeOfDaySample> {
        let root = &code.player_root;
        let layer = read_object_pointer_field(process, hero, root.layer_offset).ok()?;
        let layer_bytes = read_process_bytes(process, layer, 8).ok()?;
        let layer_type = read_u64_le(&layer_bytes, 0).ok()? as usize;
        if layer == 0 || layer_type != code.types_address + GAME_LAYER_TYPE_INDEX * 32 {
            return None;
        }
        let world = read_object_pointer_field(process, layer, root.game_layer_world_offset).ok()?;
        if world == 0
            || !object_is_a(
                process,
                world,
                code.types_address + WORLD_TYPE_INDEX * 32,
            )
        {
            return None;
        }
        let tod =
            read_object_pointer_field(process, world, root.world_time_of_day_offset).ok()?;
        if tod == 0
            || !object_is_a(
                process,
                tod,
                code.types_address + TIME_OF_DAY_TYPE_INDEX * 32,
            )
        {
            return None;
        }
        let speed = read_f64_le(
            &read_process_bytes(process, tod + root.time_of_day_speed_offset, 8).ok()?,
            0,
        )
        .ok()?;
        let paused = read_process_bytes(process, tod + root.time_of_day_paused_offset, 1)
            .ok()
            .map(|bytes| bytes[0] != 0)
            .unwrap_or(false);
        let elapsed = read_f64_le(
            &read_process_bytes(process, tod + root.time_of_day_elapsed_offset, 8).ok()?,
            0,
        )
        .ok()?;
        let prev_factor = read_f64_le(
            &read_process_bytes(process, tod + root.time_of_day_prev_factor_offset, 8).ok()?,
            0,
        )
        .ok()?;
        if ![speed, elapsed, prev_factor]
            .iter()
            .all(|value| value.is_finite())
        {
            return None;
        }
        let factor = prev_factor.rem_euclid(1.0);
        Some(TimeOfDaySample {
            factor,
            elapsed,
            speed,
            paused,
        })
    }

    fn read_nearby_enemies(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hero: usize,
        player_x: f64,
        player_y: f64,
        player_z: f64,
    ) -> Result<Vec<EnemySample>, String> {
        let root = &code.player_root;
        let layer = read_object_pointer_field(process, hero, root.layer_offset)?;
        if layer == 0
            || read_u64_le(&read_process_bytes(process, layer, 8)?, 0)? as usize
                != code.types_address + GAME_LAYER_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let units = read_object_pointer_field(process, layer, root.game_layer_units_offset)?;
        if units == 0
            || read_u64_le(&read_process_bytes(process, units, 8)?, 0)? as usize
                != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let length = i32::from_le_bytes(
            read_process_bytes(process, units + root.array_length_offset, 4)?
                .try_into()
                .unwrap(),
        );
        if !(0..=2_000).contains(&length) {
            return Err("GameLayer.units has an invalid length".to_owned());
        }
        let storage = read_object_pointer_field(process, units, root.array_storage_offset)?;
        if storage == 0 {
            return Ok(Vec::new());
        }
        let foe_type = code.types_address + FOE_TYPE_INDEX * 32;
        let radius_sq = ENEMY_SWEEP_RADIUS * ENEMY_SWEEP_RADIUS;
        let mut enemies = Vec::new();
        for index in 0..length as usize {
            if enemies.len() >= ENEMY_SWEEP_MAX {
                break;
            }
            let Some(entry) = storage.checked_add(24 + index * 8) else {
                continue;
            };
            let Ok(entry_bytes) = read_process_bytes(process, entry, 8) else {
                continue;
            };
            let Ok(unit) = read_u64_le(&entry_bytes, 0).map(|value| value as usize) else {
                continue;
            };
            if unit == 0 || unit == hero || !object_is_a(process, unit, foe_type) {
                continue;
            }
            let Ok(removed) = read_process_bytes(process, unit + root.state_removed_offset, 1) else {
                continue;
            };
            if removed[0] != 0 {
                continue;
            }
            let Ok(summon_owner) =
                read_object_pointer_field(process, unit, root.foe_summon_owner_offset)
            else {
                continue;
            };
            if summon_owner != 0 {
                continue;
            }
            let Ok(x_bytes) = read_process_bytes(process, unit + root.position_x_offset, 8) else {
                continue;
            };
            let Ok(y_bytes) = read_process_bytes(process, unit + root.position_y_offset, 8) else {
                continue;
            };
            let Ok(z_bytes) = read_process_bytes(process, unit + root.position_z_offset, 8) else {
                continue;
            };
            let Ok(x) = read_f64_le(&x_bytes, 0) else {
                continue;
            };
            let Ok(y) = read_f64_le(&y_bytes, 0) else {
                continue;
            };
            let Ok(z) = read_f64_le(&z_bytes, 0) else {
                continue;
            };
            if [x, y, z]
                .iter()
                .any(|value| !value.is_finite() || value.abs() > 10_000_000.0)
            {
                continue;
            }
            let dx = x - player_x;
            let dy = y - player_y;
            if dx * dx + dy * dy > radius_sq {
                continue;
            }
            if (z - player_z).abs() > ENEMY_SWEEP_Z_CULL {
                continue;
            }
            let kind = read_object_pointer_field(process, unit, root.unit_kind_offset)
                .ok()
                .and_then(|kind_pointer| {
                    read_hashlink_identifier(
                        process,
                        code.types_address,
                        kind_pointer,
                        "enemy unit kind",
                    )
                    .ok()
                })
                .unwrap_or_default();
            enemies.push(EnemySample {
                address: unit,
                kind,
                x: (x * 10.0).round() / 10.0,
                y: (y * 10.0).round() / 10.0,
                z: (z * 10.0).round() / 10.0,
            });
        }
        Ok(enemies)
    }

    /// Full GameLayer hero roster for the Players page / map (non-party).
    ///
    /// Matches FareverMeter `sweepWorld`: walk `units` then `entities`, keep
    /// live `ent.Hero` objects, **no XY/Z radius cull**. Distance is for UI
    /// sort/display only. Party heroes stay excluded here so map amber dots
    /// remain “others”; the Players page merges party/self in UI.
    /// Prefer `Hero.name` like the meter; enrich from `Hero.player` when it is
    /// a live `st.Player` (uid / alternate display name).
    fn read_layer_players(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hero: usize,
        local_player: usize,
        excluded_heroes: &[usize],
        player_x: f64,
        player_y: f64,
        _player_z: f64,
    ) -> Result<Vec<LayerPlayerSample>, String> {
        let root = &code.player_root;
        let layer = read_object_pointer_field(process, hero, root.layer_offset)?;
        if layer == 0
            || read_u64_le(&read_process_bytes(process, layer, 8)?, 0)? as usize
                != code.types_address + GAME_LAYER_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let hero_type = code.types_address + HERO_TYPE_INDEX * 32;
        let player_type = code.types_address + PLAYER_TYPE_INDEX * 32;
        let mut players = Vec::new();
        let mut seen = HashSet::new();
        for array_offset in [
            root.game_layer_units_offset,
            root.game_layer_entities_offset,
        ] {
            append_layer_heroes_from_array(
                process,
                code,
                root,
                layer,
                array_offset,
                hero,
                local_player,
                excluded_heroes,
                hero_type,
                player_type,
                player_x,
                player_y,
                &mut seen,
                &mut players,
            )?;
            if players.len() >= PLAYER_SWEEP_MAX {
                break;
            }
        }
        Ok(players)
    }

    fn append_layer_heroes_from_array(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        layer: usize,
        array_field_offset: usize,
        local_hero: usize,
        local_player: usize,
        excluded_heroes: &[usize],
        hero_type: usize,
        player_type: usize,
        player_x: f64,
        player_y: f64,
        seen: &mut HashSet<usize>,
        players: &mut Vec<LayerPlayerSample>,
    ) -> Result<(), String> {
        let units = read_object_pointer_field(process, layer, array_field_offset)?;
        if units == 0
            || read_u64_le(&read_process_bytes(process, units, 8)?, 0)? as usize
                != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32
        {
            return Ok(());
        }
        let length = i32::from_le_bytes(
            read_process_bytes(process, units + root.array_length_offset, 4)?
                .try_into()
                .unwrap(),
        );
        if length <= 0 {
            return Ok(());
        }
        if length > PLAYER_ARRAY_LENGTH_MAX {
            return Err("GameLayer player array has an invalid length".to_owned());
        }
        let storage = read_object_pointer_field(process, units, root.array_storage_offset)?;
        if storage == 0 {
            return Ok(());
        }
        for index in 0..length as usize {
            if players.len() >= PLAYER_SWEEP_MAX {
                break;
            }
            let Some(entry) = storage.checked_add(24 + index * 8) else {
                continue;
            };
            let Ok(entry_bytes) = read_process_bytes(process, entry, 8) else {
                continue;
            };
            let Ok(unit) = read_u64_le(&entry_bytes, 0).map(|value| value as usize) else {
                continue;
            };
            if unit == 0 || unit == local_hero || !object_is_a(process, unit, hero_type) {
                continue;
            }
            if !seen.insert(unit) {
                continue;
            }
            if excluded_heroes.contains(&unit) {
                continue;
            }
            let Ok(removed) = read_process_bytes(process, unit + root.state_removed_offset, 1) else {
                continue;
            };
            if removed[0] != 0 {
                continue;
            }
            let Ok(x_bytes) = read_process_bytes(process, unit + root.position_x_offset, 8) else {
                continue;
            };
            let Ok(y_bytes) = read_process_bytes(process, unit + root.position_y_offset, 8) else {
                continue;
            };
            let Ok(z_bytes) = read_process_bytes(process, unit + root.position_z_offset, 8) else {
                continue;
            };
            let Ok(rot_bytes) = read_process_bytes(process, unit + root.rotation_z_offset, 8) else {
                continue;
            };
            let Ok(x) = read_f64_le(&x_bytes, 0) else {
                continue;
            };
            let Ok(y) = read_f64_le(&y_bytes, 0) else {
                continue;
            };
            let Ok(z) = read_f64_le(&z_bytes, 0) else {
                continue;
            };
            let Ok(rotation) = read_f64_le(&rot_bytes, 0) else {
                continue;
            };
            if [x, y, z, rotation]
                .iter()
                .any(|value| !value.is_finite() || value.abs() > 10_000_000.0)
            {
                continue;
            }
            let dx = x - player_x;
            let dy = y - player_y;
            let distance = ((dx * dx + dy * dy).sqrt() * 10.0).round() / 10.0;

            // Meter identity is Hero.name. Player fields are optional enrichment.
            let hero_name_pointer =
                read_object_pointer_field(process, unit, root.hero_name_offset).unwrap_or(0);
            let hero_name = read_hashlink_string(
                process,
                code.types_address,
                hero_name_pointer,
                "layer hero name",
            )
            .unwrap_or_default();
            let mut player_name = String::new();
            let mut uid = String::new();
            if let Ok(owner) = read_object_pointer_field(process, unit, root.hero_player_offset) {
                if owner != 0
                    && owner != local_player
                    && read_u64_le(&read_process_bytes(process, owner, 8).unwrap_or_default(), 0)
                        .map(|value| value as usize)
                        .unwrap_or(0)
                        == player_type
                {
                    let name_pointer =
                        read_object_pointer_field(process, owner, root.player_name_offset)
                            .unwrap_or(0);
                    let uid_pointer =
                        read_object_pointer_field(process, owner, root.player_uid_offset)
                            .unwrap_or(0);
                    player_name = read_hashlink_string(
                        process,
                        code.types_address,
                        name_pointer,
                        "layer player name",
                    )
                    .unwrap_or_default();
                    uid = read_hashlink_string(
                        process,
                        code.types_address,
                        uid_pointer,
                        "layer player uid",
                    )
                    .unwrap_or_default();
                }
            }
            let name = pick_player_display_name(&player_name, &hero_name);
            if name.is_empty() {
                continue;
            }
            let class_name = read_object_pointer_field(process, unit, root.unit_kind_offset)
                .ok()
                .and_then(|kind_pointer| {
                    read_hashlink_identifier(
                        process,
                        code.types_address,
                        kind_pointer,
                        "layer player unit kind",
                    )
                    .ok()
                })
                .unwrap_or_default();
            let class_name = if looks_like_element_kind_id(&class_name) {
                String::new()
            } else {
                class_name
            };
            let level = i32::from_le_bytes(
                read_process_bytes(process, unit + root.level_offset, 4)
                    .unwrap_or_else(|_| vec![0, 0, 0, 0])
                    .try_into()
                    .unwrap_or([0, 0, 0, 0]),
            );
            let level = if (1..=10_000).contains(&level) {
                level
            } else {
                0
            };
            players.push(LayerPlayerSample {
                address: unit,
                name,
                uid,
                class_name,
                level,
                x: (x * 10.0).round() / 10.0,
                y: (y * 10.0).round() / 10.0,
                z: (z * 10.0).round() / 10.0,
                rotation: (rotation * 1_000.0).round() / 1_000.0,
                distance,
            });
        }
        Ok(())
    }

    fn classify_gatherable_category(kind: &str) -> &'static str {
        let lower = kind.to_ascii_lowercase();
        if lower.contains("ore")
            || lower.contains("tungstene")
            || lower.contains("copper")
            || lower.contains("iron")
            || lower.contains("tin")
        {
            return "ore";
        }
        if lower.contains("plant")
            || lower.contains("madrigold")
            || lower.contains("lavendula")
            || lower.contains("thyme")
            || lower.contains("zealotus")
        {
            return "plant";
        }
        "gatherable"
    }

    /// Nearby gatherables / chests for Atlas map markers.
    ///
    /// Walks `st.GameLayer.interactibles`, keeps live Gatherable and Chest
    /// objects, and culls by radius / z like the enemy sweep.
    fn read_nearby_interactibles(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hero: usize,
        player_x: f64,
        player_y: f64,
        player_z: f64,
    ) -> Result<Vec<InteractibleSample>, String> {
        let root = &code.player_root;
        let layer = read_object_pointer_field(process, hero, root.layer_offset)?;
        if layer == 0
            || read_u64_le(&read_process_bytes(process, layer, 8)?, 0)? as usize
                != code.types_address + GAME_LAYER_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let interactibles =
            read_object_pointer_field(process, layer, root.game_layer_interactibles_offset)?;
        if interactibles == 0
            || read_u64_le(&read_process_bytes(process, interactibles, 8)?, 0)? as usize
                != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32
        {
            return Ok(Vec::new());
        }
        let length = i32::from_le_bytes(
            read_process_bytes(process, interactibles + root.array_length_offset, 4)?
                .try_into()
                .unwrap(),
        );
        if !(0..=4_000).contains(&length) {
            return Err("GameLayer.interactibles has an invalid length".to_owned());
        }
        let storage = read_object_pointer_field(process, interactibles, root.array_storage_offset)?;
        if storage == 0 {
            return Ok(Vec::new());
        }
        let gatherable_type = code.types_address + GATHERABLE_TYPE_INDEX * 32;
        let chest_type = code.types_address + CHEST_TYPE_INDEX * 32;
        let radius_sq = INTERACTIBLE_SWEEP_RADIUS * INTERACTIBLE_SWEEP_RADIUS;
        let mut samples = Vec::new();
        for index in 0..length as usize {
            if samples.len() >= INTERACTIBLE_SWEEP_MAX {
                break;
            }
            let Some(entry) = storage.checked_add(24 + index * 8) else {
                continue;
            };
            let Ok(entry_bytes) = read_process_bytes(process, entry, 8) else {
                continue;
            };
            let Ok(object) = read_u64_le(&entry_bytes, 0).map(|value| value as usize) else {
                continue;
            };
            if object == 0 {
                continue;
            }
            let is_gatherable = object_is_a(process, object, gatherable_type);
            let is_chest = !is_gatherable && object_is_a(process, object, chest_type);
            if !is_gatherable && !is_chest {
                continue;
            }
            let Ok(removed) = read_process_bytes(process, object + root.state_removed_offset, 1)
            else {
                continue;
            };
            if removed[0] != 0 {
                continue;
            }
            let Ok(enabled) =
                read_process_bytes(process, object + root.interactible_enabled_offset, 1)
            else {
                continue;
            };
            if enabled[0] == 0 {
                continue;
            }
            let Ok(x_bytes) = read_process_bytes(process, object + root.position_x_offset, 8) else {
                continue;
            };
            let Ok(y_bytes) = read_process_bytes(process, object + root.position_y_offset, 8) else {
                continue;
            };
            let Ok(z_bytes) = read_process_bytes(process, object + root.position_z_offset, 8) else {
                continue;
            };
            let Ok(x) = read_f64_le(&x_bytes, 0) else {
                continue;
            };
            let Ok(y) = read_f64_le(&y_bytes, 0) else {
                continue;
            };
            let Ok(z) = read_f64_le(&z_bytes, 0) else {
                continue;
            };
            if [x, y, z]
                .iter()
                .any(|value| !value.is_finite() || value.abs() > 10_000_000.0)
            {
                continue;
            }
            let dx = x - player_x;
            let dy = y - player_y;
            if dx * dx + dy * dy > radius_sq {
                continue;
            }
            if (z - player_z).abs() > INTERACTIBLE_SWEEP_Z_CULL {
                continue;
            }
            let name = read_object_pointer_field(process, object, root.element_kind_offset)
                .ok()
                .and_then(|kind_pointer| {
                    read_hashlink_identifier(
                        process,
                        code.types_address,
                        kind_pointer,
                        "interactible kind",
                    )
                    .or_else(|_| {
                        read_hashlink_string(
                            process,
                            code.types_address,
                            kind_pointer,
                            "interactible kind",
                        )
                    })
                    .ok()
                })
                .unwrap_or_default();
            let category = if is_chest {
                "chest"
            } else {
                classify_gatherable_category(&name)
            };
            samples.push(InteractibleSample {
                address: object,
                category,
                name,
                x: (x * 10.0).round() / 10.0,
                y: (y * 10.0).round() / 10.0,
                z: (z * 10.0).round() / 10.0,
            });
        }
        Ok(samples)
    }

    fn read_player_root(
        process: &OwnedHandle,
        types_address: usize,
        globals_address: usize,
        globals_indexes_address: usize,
        globals_data_address: usize,
        require_live_player: bool,
    ) -> Result<PlayerRoot, String> {
        let app_static_type_address = types_address + APP_STATIC_TYPE_INDEX * 32;
        let app_global_type = read_u64_le(
            &read_process_bytes(process, globals_address + APP_STATIC_GLOBAL_INDEX * 8, 8)?,
            0,
        )? as usize;
        if app_global_type != app_static_type_address {
            return Err("global 955 is not typed as $App".to_owned());
        }
        let app_global_offset = read_u32_le(
            &read_process_bytes(
                process,
                globals_indexes_address + APP_STATIC_GLOBAL_INDEX * 4,
                4,
            )?,
            0,
        )? as usize;
        let app_static_holder_address =
            read_object_pointer_field(process, globals_data_address, app_global_offset)?;
        if app_static_holder_address == 0
            || read_u64_le(
                &read_process_bytes(process, app_static_holder_address, 8)?,
                0,
            )? as usize
                != app_static_type_address
        {
            return Err("$App static holder failed its runtime type check".to_owned());
        }

        let app_instance_offset =
            object_field_offset(process, app_static_type_address, APP_INSTANCE_FIELD_INDEX)?;
        let game_app_type_address = types_address + GAME_APP_TYPE_INDEX * 32;
        let player_offset =
            object_field_offset(process, game_app_type_address, GAME_APP_PLAYER_FIELD_INDEX)?;
        let hero_offset =
            object_field_offset(process, game_app_type_address, GAME_APP_HERO_FIELD_INDEX)?;
        let gui_offset =
            object_field_offset(process, game_app_type_address, GAME_APP_GUI_FIELD_INDEX)?;
        let game_camera_offset = object_field_offset(
            process,
            game_app_type_address,
            GAME_APP_GAME_CAMERA_FIELD_INDEX,
        )?;
        let camera_offset =
            object_field_offset(process, game_app_type_address, GAME_APP_CAMERA_FIELD_INDEX)?;
        let base_camera_type_address = types_address + BASE_CAMERA_TYPE_INDEX * 32;
        let camera_abs_pos_offset = object_field_offset(
            process,
            base_camera_type_address,
            BASE_CAMERA_ABS_POS_FIELD_INDEX,
        )?;
        let matrix_type_address = types_address + MATRIX_IMPL_TYPE_INDEX * 32;
        let matrix_tx_offset =
            object_field_offset(process, matrix_type_address, MATRIX_TX_FIELD_INDEX)?;
        let matrix_ty_offset =
            object_field_offset(process, matrix_type_address, MATRIX_TY_FIELD_INDEX)?;
        let camera_cur_direction_offset = object_field_offset(
            process,
            base_camera_type_address,
            BASE_CAMERA_CUR_DIRECTION_FIELD_INDEX,
        )?;
        let camera_direction_offset = object_field_offset(
            process,
            base_camera_type_address,
            BASE_CAMERA_DIRECTION_FIELD_INDEX,
        )?;

        let game_app_address =
            read_object_pointer_field(process, app_static_holder_address, app_instance_offset)?;
        let game_app_live = game_app_address != 0
            && read_u64_le(&read_process_bytes(process, game_app_address, 8)?, 0)? as usize
                == game_app_type_address;
        if require_live_player && !game_app_live {
            return Err("$App.inst is not a live GameApp object".to_owned());
        }

        let (player_address, hero_address) = if game_app_live {
            (
                read_object_pointer_field(process, game_app_address, player_offset)?,
                read_object_pointer_field(process, game_app_address, hero_offset)?,
            )
        } else {
            (0, 0)
        };
        let player_live = player_address != 0
            && read_u64_le(&read_process_bytes(process, player_address, 8)?, 0)? as usize
                == types_address + PLAYER_TYPE_INDEX * 32;
        let hero_live = hero_address != 0
            && read_u64_le(&read_process_bytes(process, hero_address, 8)?, 0)? as usize
                == types_address + HERO_TYPE_INDEX * 32;
        if require_live_player && !player_live {
            return Err("GameApp.me is not a live st.Player object".to_owned());
        }
        if require_live_player && !hero_live {
            return Err("GameApp.hero is not a live ent.Hero object".to_owned());
        }

        let hero_type_address = types_address + HERO_TYPE_INDEX * 32;
        let position_x_offset =
            object_field_offset(process, hero_type_address, HERO_POS_X_FIELD_INDEX)?;
        let position_y_offset =
            object_field_offset(process, hero_type_address, HERO_POS_Y_FIELD_INDEX)?;
        let position_z_offset =
            object_field_offset(process, hero_type_address, HERO_POS_Z_FIELD_INDEX)?;
        let rotation_z_offset =
            object_field_offset(process, hero_type_address, HERO_ROTATION_Z_FIELD_INDEX)?;
        let layer_offset =
            object_field_offset(process, hero_type_address, HERO_LAYER_FIELD_INDEX)?;
        let game_layer_type_address = types_address + GAME_LAYER_TYPE_INDEX * 32;
        let game_layer_world_offset = object_field_offset(
            process,
            game_layer_type_address,
            GAME_LAYER_WORLD_FIELD_INDEX,
        )?;
        let game_layer_main_activity_offset = object_field_offset(
            process,
            game_layer_type_address,
            GAME_LAYER_MAIN_ACTIVITY_FIELD_INDEX,
        )?;
        let game_layer_is_rift_offset = object_field_offset(
            process,
            game_layer_type_address,
            GAME_LAYER_IS_RIFT_FIELD_INDEX,
        )?;
        let game_layer_interactibles_offset = object_field_offset(
            process,
            game_layer_type_address,
            GAME_LAYER_INTERACTIBLES_FIELD_INDEX,
        )?;
        let game_layer_entities_offset = object_field_offset(
            process,
            game_layer_type_address,
            GAME_LAYER_ENTITIES_FIELD_INDEX,
        )?;
        let game_layer_units_offset = object_field_offset(
            process,
            game_layer_type_address,
            GAME_LAYER_UNITS_FIELD_INDEX,
        )?;
        let world_type_address = types_address + WORLD_TYPE_INDEX * 32;
        let world_level_offset =
            object_field_offset(process, world_type_address, WORLD_LEVEL_FIELD_INDEX)?;
        let world_time_of_day_offset = object_field_offset(
            process,
            world_type_address,
            WORLD_TIME_OF_DAY_FIELD_INDEX,
        )?;
        let world_is_world_map_offset = object_field_offset(
            process,
            world_type_address,
            WORLD_IS_WORLD_MAP_FIELD_INDEX,
        )?;
        let time_of_day_type_address = types_address + TIME_OF_DAY_TYPE_INDEX * 32;
        let time_of_day_speed_offset = object_field_offset(
            process,
            time_of_day_type_address,
            TIME_OF_DAY_SPEED_FIELD_INDEX,
        )?;
        let time_of_day_paused_offset = object_field_offset(
            process,
            time_of_day_type_address,
            TIME_OF_DAY_PAUSED_FIELD_INDEX,
        )?;
        let time_of_day_elapsed_offset = object_field_offset(
            process,
            time_of_day_type_address,
            TIME_OF_DAY_ELAPSED_FIELD_INDEX,
        )?;
        let time_of_day_prev_factor_offset = object_field_offset(
            process,
            time_of_day_type_address,
            TIME_OF_DAY_PREV_FACTOR_FIELD_INDEX,
        )?;
        let activity_kind_offset = object_field_offset(
            process,
            types_address + ACTIVITY_TYPE_INDEX * 32,
            ACTIVITY_KIND_FIELD_INDEX,
        )?;
        let state_removed_offset = object_field_offset(
            process,
            types_address + STATE_TYPE_INDEX * 32,
            STATE_REMOVED_FIELD_INDEX,
        )?;
        let interactible_enabled_offset = object_field_offset(
            process,
            types_address + GATHERABLE_TYPE_INDEX * 32,
            INTERACTIBLE_ENABLED_FIELD_INDEX,
        )?;
        let element_kind_offset = object_field_offset(
            process,
            types_address + GATHERABLE_TYPE_INDEX * 32,
            ELEMENT_KIND_FIELD_INDEX,
        )?;
        let foe_summon_owner_offset = object_field_offset(
            process,
            types_address + FOE_TYPE_INDEX * 32,
            FOE_SUMMON_OWNER_FIELD_INDEX,
        )?;
        let player_name_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_NAME_FIELD_INDEX,
        )?;
        let player_uid_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_UID_FIELD_INDEX,
        )?;
        let hero_player_offset =
            object_field_offset(process, hero_type_address, HERO_PLAYER_FIELD_INDEX)?;
        let hero_name_offset =
            object_field_offset(process, hero_type_address, HERO_NAME_FIELD_INDEX)?;
        let player_group_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_GROUP_FIELD_INDEX,
        )?;
        let player_progress_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_PROGRESS_FIELD_INDEX,
        )?;
        let player_hero_data_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_HERO_DATA_FIELD_INDEX,
        )?;
        let player_hero_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_HERO_FIELD_INDEX,
        )?;
        let player_connected_offset = object_field_offset(
            process,
            types_address + PLAYER_TYPE_INDEX * 32,
            PLAYER_CONNECTED_FIELD_INDEX,
        )?;
        let attributes_offset =
            object_field_offset(process, hero_type_address, UNIT_ATTRIBUTES_FIELD_INDEX)?;
        let level_offset = object_field_offset(process, hero_type_address, UNIT_LEVEL_FIELD_INDEX)?;
        let in_combat_offset =
            object_field_offset(process, hero_type_address, UNIT_IN_COMBAT_FIELD_INDEX)?;
        let unit_kind_offset =
            object_field_offset(process, hero_type_address, UNIT_KIND_FIELD_INDEX)?;
        let attributes_type_address = types_address + UNIT_ATTRIBUTES_TYPE_INDEX * 32;
        let vitality_offset =
            object_field_offset(process, attributes_type_address, ATTR_VITALITY_FIELD_INDEX)?;
        let health_offset =
            object_field_offset(process, attributes_type_address, ATTR_HEALTH_FIELD_INDEX)?;
        let last_resource_max_offset = object_field_offset(
            process,
            attributes_type_address,
            ATTR_LAST_RESOURCE_MAX_FIELD_INDEX,
        )?;
        let int_map_handle_offset = object_field_offset(
            process,
            types_address + INT_MAP_TYPE_INDEX * 32,
            INT_MAP_HANDLE_FIELD_INDEX,
        )?;
        let max_health_offset = object_field_offset(
            process,
            attributes_type_address,
            ATTR_MAX_HEALTH_FIELD_INDEX,
        )?;
        let health_regen_offset = object_field_offset(
            process,
            attributes_type_address,
            ATTR_HEALTH_REGEN_FIELD_INDEX,
        )?;
        let shield_offset =
            object_field_offset(process, attributes_type_address, ATTR_SHIELD_FIELD_INDEX)?;
        let special_energy_offset = object_field_offset(
            process,
            attributes_type_address,
            ATTR_SPECIAL_ENERGY_FIELD_INDEX,
        )?;
        let special_energy_regen_offset = object_field_offset(
            process,
            attributes_type_address,
            ATTR_SPECIAL_ENERGY_REGEN_FIELD_INDEX,
        )?;
        let widgets_offset = object_field_offset(
            process,
            types_address + GAME_UI_TYPE_INDEX * 32,
            BASE_UI_WIDGETS_FIELD_INDEX,
        )?;
        let game_ui_game_root_offset = object_field_offset(
            process,
            types_address + GAME_UI_TYPE_INDEX * 32,
            GAME_UI_GAME_ROOT_FIELD_INDEX,
        )?;
        let game_ui_root_hud_offset = object_field_offset(
            process,
            types_address + GAME_UI_ROOT_TYPE_INDEX * 32,
            GAME_UI_ROOT_HUD_FIELD_INDEX,
        )?;
        let widget_container_offset = object_field_offset(
            process,
            types_address + 1_209 * 32,
            WIDGET_CONTAINER_FIELD_INDEX,
        )?;
        let h2d_children_offset = object_field_offset(
            process,
            types_address + H2D_OBJECT_TYPE_INDEX * 32,
            H2D_OBJECT_CHILDREN_FIELD_INDEX,
        )?;
        let h2d_parent_offset = object_field_offset(
            process,
            types_address + H2D_OBJECT_TYPE_INDEX * 32,
            H2D_OBJECT_PARENT_FIELD_INDEX,
        )?;
        let h2d_visible_offset = object_field_offset(
            process,
            types_address + H2D_OBJECT_TYPE_INDEX * 32,
            H2D_OBJECT_VISIBLE_FIELD_INDEX,
        )?;
        let array_length_offset = object_field_offset(
            process,
            types_address + ARRAY_OBJ_TYPE_INDEX * 32,
            ARRAY_LENGTH_FIELD_INDEX,
        )?;
        let array_storage_offset = object_field_offset(
            process,
            types_address + ARRAY_OBJ_TYPE_INDEX * 32,
            ARRAY_STORAGE_FIELD_INDEX,
        )?;
        let array_proxy_array_offset = object_field_offset(
            process,
            types_address + ARRAY_PROXY_TYPE_INDEX * 32,
            ARRAY_PROXY_ARRAY_FIELD_INDEX,
        )?;
        let array_dyn_array_offset = object_field_offset(
            process,
            types_address + ARRAY_DYN_TYPE_INDEX * 32,
            ARRAY_DYN_ARRAY_FIELD_INDEX,
        )?;
        let group_players_offset = object_field_offset(
            process,
            types_address + GROUP_TYPE_INDEX * 32,
            GROUP_PLAYERS_FIELD_INDEX,
        )?;
        let progress_counters_offset = object_field_offset(
            process,
            types_address + PROGRESS_TYPE_INDEX * 32,
            PROGRESS_COUNTERS_FIELD_INDEX,
        )?;
        let progress_elements_offset = object_field_offset(
            process,
            types_address + PROGRESS_TYPE_INDEX * 32,
            PROGRESS_ELEMENTS_FIELD_INDEX,
        )?;
        let map_data_map_offset = object_field_offset(
            process,
            types_address + MAP_DATA_TYPE_INDEX * 32,
            MAP_DATA_MAP_FIELD_INDEX,
        )?;
        let string_map_handle_offset = object_field_offset(
            process,
            types_address + STRING_MAP_TYPE_INDEX * 32,
            STRING_MAP_HANDLE_FIELD_INDEX,
        )?;
        let completion_proxy_completed_offset = object_field_offset(
            process,
            types_address + COMPLETION_PROXY_TYPE_INDEX * 32,
            COMPLETION_PROXY_COMPLETED_FIELD_INDEX,
        )?;
        let hero_data_currencies_offset = object_field_offset(
            process,
            types_address + HERO_DATA_TYPE_INDEX * 32,
            HERO_DATA_CURRENCIES_FIELD_INDEX,
        )?;
        let hero_data_progress_offset = object_field_offset(
            process,
            types_address + HERO_DATA_TYPE_INDEX * 32,
            HERO_DATA_PROGRESS_FIELD_INDEX,
        )?;
        let hero_loadout_offset = object_field_offset(
            process,
            types_address + HERO_TYPE_INDEX * 32,
            HERO_LOADOUT_FIELD_INDEX,
        )?;
        let loadout_currencies_offset = object_field_offset(
            process,
            types_address + LOADOUT_TYPE_INDEX * 32,
            LOADOUT_CURRENCIES_FIELD_INDEX,
        )?;
        let hero_widget_hero_offset = object_field_offset(
            process,
            types_address + HERO_WIDGET_TYPE_INDEX * 32,
            HERO_WIDGET_HERO_FIELD_INDEX,
        )?;
        let hero_widget_health_bar_offset = object_field_offset(
            process,
            types_address + HERO_WIDGET_TYPE_INDEX * 32,
            HERO_WIDGET_HEALTH_BAR_FIELD_INDEX,
        )?;
        let health_bar_health_gauge_offset = object_field_offset(
            process,
            types_address + HEALTH_BAR_TYPE_INDEX * 32,
            HEALTH_BAR_HEALTH_GAUGE_FIELD_INDEX,
        )?;
        let health_bar_shield_gauge_offset = object_field_offset(
            process,
            types_address + HEALTH_BAR_TYPE_INDEX * 32,
            HEALTH_BAR_SHIELD_GAUGE_FIELD_INDEX,
        )?;
        let base_gauge_max_offset = object_field_offset(
            process,
            types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32,
            BASE_GAUGE_MAX_FIELD_INDEX,
        )?;
        let base_gauge_value_offset = object_field_offset(
            process,
            types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32,
            BASE_GAUGE_VALUE_FIELD_INDEX,
        )?;
        let attribute_bar_unit_offset = object_field_offset(
            process,
            types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32,
            ATTRIBUTE_BAR_UNIT_FIELD_INDEX,
        )?;
        let attribute_bar_id_offset = object_field_offset(
            process,
            types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32,
            ATTRIBUTE_BAR_ID_FIELD_INDEX,
        )?;
        let (position_x, position_y, position_z, rotation_z) = if hero_live {
            let position_x = read_f64_le(
                &read_process_bytes(process, hero_address + position_x_offset, 8)?,
                0,
            )?;
            let position_y = read_f64_le(
                &read_process_bytes(process, hero_address + position_y_offset, 8)?,
                0,
            )?;
            let position_z = read_f64_le(
                &read_process_bytes(process, hero_address + position_z_offset, 8)?,
                0,
            )?;
            let rotation_z = read_f64_le(
                &read_process_bytes(process, hero_address + rotation_z_offset, 8)?,
                0,
            )?;
            if require_live_player
                && [position_x, position_y, position_z, rotation_z]
                    .iter()
                    .any(|value| !value.is_finite() || value.abs() > 10_000_000.0)
            {
                return Err("live Hero transform failed sanity validation".to_owned());
            }
            (position_x, position_y, position_z, rotation_z)
        } else {
            (0.0, 0.0, 0.0, 0.0)
        };

        Ok(PlayerRoot {
            app_static_holder_address,
            game_app_address: if game_app_live { game_app_address } else { 0 },
            player_address: if player_live { player_address } else { 0 },
            hero_address: if hero_live { hero_address } else { 0 },
            position_x,
            position_y,
            position_z,
            rotation_z,
            app_instance_offset,
            player_offset,
            hero_offset,
            gui_offset,
            game_camera_offset,
            camera_offset,
            camera_abs_pos_offset,
            matrix_tx_offset,
            matrix_ty_offset,
            camera_cur_direction_offset,
            camera_direction_offset,
            position_x_offset,
            position_y_offset,
            position_z_offset,
            rotation_z_offset,
            layer_offset,
            game_layer_world_offset,
            game_layer_main_activity_offset,
            game_layer_is_rift_offset,
            game_layer_interactibles_offset,
            game_layer_entities_offset,
            game_layer_units_offset,
            world_level_offset,
            world_time_of_day_offset,
            world_is_world_map_offset,
            time_of_day_speed_offset,
            time_of_day_paused_offset,
            time_of_day_elapsed_offset,
            time_of_day_prev_factor_offset,
            activity_kind_offset,
            state_removed_offset,
            interactible_enabled_offset,
            element_kind_offset,
            foe_summon_owner_offset,
            player_name_offset,
            player_uid_offset,
            hero_player_offset,
            hero_name_offset,
            player_group_offset,
            player_progress_offset,
            player_hero_data_offset,
            player_hero_offset,
            player_connected_offset,
            attributes_offset,
            level_offset,
            in_combat_offset,
            unit_kind_offset,
            vitality_offset,
            health_offset,
            last_resource_max_offset,
            int_map_handle_offset,
            max_health_offset,
            health_regen_offset,
            shield_offset,
            special_energy_offset,
            special_energy_regen_offset,
            widgets_offset,
            game_ui_game_root_offset,
            game_ui_root_hud_offset,
            widget_container_offset,
            h2d_children_offset,
            h2d_parent_offset,
            h2d_visible_offset,
            array_length_offset,
            array_storage_offset,
            array_proxy_array_offset,
            array_dyn_array_offset,
            group_players_offset,
            progress_counters_offset,
            progress_elements_offset,
            map_data_map_offset,
            string_map_handle_offset,
            completion_proxy_completed_offset,
            hero_data_currencies_offset,
            hero_data_progress_offset,
            hero_loadout_offset,
            loadout_currencies_offset,
            hero_widget_hero_offset,
            hero_widget_health_bar_offset,
            health_bar_health_gauge_offset,
            health_bar_shield_gauge_offset,
            base_gauge_max_offset,
            base_gauge_value_offset,
            attribute_bar_unit_offset,
            attribute_bar_id_offset,
        })
    }

    fn looks_like_element_kind_id(name: &str) -> bool {
        // Prefab/node ids: Madrigold_Small_Generic, Z1_World_…_Chest_58, etc.
        // Farever player display names do not contain '_' or '/'.
        let trimmed = name.trim();
        if trimmed.is_empty() || !trimmed.is_ascii() {
            return true;
        }
        if trimmed.contains('_') || trimmed.contains('/') {
            return true;
        }
        let lower = trimmed.to_ascii_lowercase();
        const TOKENS: &[&str] = &[
            "small",
            "medium",
            "large",
            "generic",
            "chestorb",
            "worldchest",
            "recipe",
        ];
        // Only treat token hits as prefab-like when the string also looks
        // technical (digits / long mixed case already handled by '_').
        if trimmed.chars().any(|character| character.is_ascii_digit())
            && TOKENS.iter().any(|token| lower.contains(token))
        {
            return true;
        }
        false
    }

    fn pick_player_display_name(player_name: &str, hero_name: &str) -> String {
        let player = player_name.trim();
        let hero = hero_name.trim();
        if !player.is_empty() && !looks_like_element_kind_id(player) {
            return player.to_owned();
        }
        if !hero.is_empty() && !looks_like_element_kind_id(hero) {
            return hero.to_owned();
        }
        // Never emit gatherable/node prefab ids as the player display name.
        String::new()
    }

    fn read_hashlink_string(
        process: &OwnedHandle,
        types_address: usize,
        value_address: usize,
        label: &str,
    ) -> Result<String, String> {
        if value_address == 0 {
            return Ok(String::new());
        }
        // Farever's HLB type 13 string values are GC objects. Validate the
        // wrapper type, then follow its contained UTF-16 data pointer.
        let wrapper = read_process_bytes(process, value_address, 16)?;
        let value_type = read_u64_le(&wrapper, 0)? as usize;
        let expected_type = types_address + 13 * 32;
        if value_type != expected_type {
            return Err(format!("{label} wrapper type mismatch"));
        }
        let pointer = read_u64_le(&wrapper, 8)? as usize;
        if pointer == 0 {
            return Ok(String::new());
        }
        // Character names are short. Keep this read deliberately bounded and
        // require a terminator so an invalid pointer cannot become an
        // unbounded scan. Use a partial-tolerant read: short UTF-16 buffers
        // often sit near page edges under Wine (ERROR_PARTIAL_COPY).
        let bytes = read_process_bytes_partial(process, pointer, 128)?;
        if let Some(value) = decode_utf16_z(&bytes, label)? {
            return Ok(value);
        }
        Err(format!("{label} exceeds the bounded string read"))
    }

    fn read_hashlink_identifier(
        process: &OwnedHandle,
        types_address: usize,
        value_address: usize,
        label: &str,
    ) -> Result<String, String> {
        if let Ok(value) = read_hashlink_string(process, types_address, value_address, label) {
            return Ok(value);
        }
        if value_address == 0 {
            return Ok(String::new());
        }
        let bytes = read_process_bytes_partial(process, value_address, 64)?;
        if let Some(value) = decode_utf16_z(&bytes, label)? {
            if !value.is_empty()
                && value.len() <= 31
                && value
                    .chars()
                    .all(|character| character.is_ascii_alphanumeric() || character == '_')
            {
                return Ok(value);
            }
            return Err(format!("{label} is not a bounded identifier"));
        }
        Err(format!("{label} exceeds the bounded identifier read"))
    }

    struct InstanceSample {
        /// Coarse bucket: world | rift | dungeon | instance | unknown
        kind: &'static str,
        map_id: String,
        is_rift: bool,
        is_dungeon: bool,
        is_world_map: bool,
        activity_kind: String,
    }

    struct TimeOfDaySample {
        /// Lighting/day-cycle factor in [0, 1) from world.TimeOfDay.prevFactor.
        factor: f64,
        elapsed: f64,
        speed: f64,
        paused: bool,
    }

    struct CurrencySample {
        kind: String,
        amount: i64,
    }

    struct TelemetrySample {
        game_app: usize,
        player: usize,
        hero: usize,
        name: String,
        uid: String,
        class_name: String,
        level: i32,
        in_combat: bool,
        health: f64,
        vitality: f64,
        max_health: f64,
        health_regen: f64,
        shield: f64,
        shield_ratio: f64,
        shield_capacity: f64,
        shield_gauge_visible: bool,
        raw_shield: f64,
        shield_gauge_available: bool,
        special_energy: f64,
        special_energy_regen: f64,
        currencies: Vec<CurrencySample>,
        /// Live Progress.counters used for tiered currency caps (e.g. souls).
        currency_counters: Vec<(String, i64)>,
        x: f64,
        y: f64,
        z: f64,
        rotation: f64,
        /// BaseCamera.curDirection — view yaw in radians (same frame as rotation_z).
        camera_yaw: f64,
        party: Vec<PartySample>,
        /// Hero object addresses for party members (excludes self).
        party_heroes: Vec<usize>,
        instance: InstanceSample,
        time_of_day: Option<TimeOfDaySample>,
        completed_elements: Vec<String>,
    }

    struct PartySample {
        name: String,
        uid: String,
        class_name: String,
        level: i32,
        connected: bool,
        health: f64,
        max_health: f64,
        shield: f64,
        x: f64,
        y: f64,
        z: f64,
        rotation: f64,
        distance: f64,
    }

    #[derive(Clone, Copy)]
    struct PartyGaugeCache {
        hero: usize,
        health: Option<usize>,
        shield: Option<usize>,
    }

    fn wrap_angle_rad(yaw: f64) -> f64 {
        if !yaw.is_finite() {
            return f64::NAN;
        }
        let wrapped = yaw.rem_euclid(std::f64::consts::TAU);
        if wrapped > std::f64::consts::PI {
            wrapped - std::f64::consts::TAU
        } else {
            wrapped
        }
    }

    fn read_camera_yaw(
        process: &OwnedHandle,
        code: &CodeAnchor,
        game_app: usize,
        hero_x: f64,
        hero_y: f64,
    ) -> f64 {
        let root = &code.player_root;
        if game_app == 0 {
            return f64::NAN;
        }
        let game_camera_type = code.types_address + GAME_CAMERA_TYPE_INDEX * 32;
        let base_camera_type = code.types_address + BASE_CAMERA_TYPE_INDEX * 32;
        let candidates = [root.game_camera_offset, root.camera_offset];
        for offset in candidates {
            let Ok(camera) = read_object_pointer_field(process, game_app, offset) else {
                continue;
            };
            if camera == 0 {
                continue;
            }
            let Ok(type_bytes) = read_process_bytes(process, camera, 8) else {
                continue;
            };
            let Ok(camera_type) = read_u64_le(&type_bytes, 0).map(|value| value as usize) else {
                continue;
            };
            if camera_type != game_camera_type
                && camera_type != base_camera_type
                && !object_is_a(process, camera, base_camera_type)
            {
                continue;
            }

            // Prefer yaw from camera eye → hero (third-person look-at on XY).
            // Use absPos world translation; local Object.x/y can be parent-relative.
            // curDirection alone can sit on a stale value across samples.
            // On absPos faults, fall through to curDirection for this camera —
            // do not abandon the candidate before the direction fallback.
            if hero_x.is_finite() && hero_y.is_finite() {
                if let Ok(abs_pos) =
                    read_object_pointer_field(process, camera, root.camera_abs_pos_offset)
                {
                    if abs_pos != 0 {
                        if let (Ok(x_bytes), Ok(y_bytes)) = (
                            read_process_bytes(process, abs_pos + root.matrix_tx_offset, 8),
                            read_process_bytes(process, abs_pos + root.matrix_ty_offset, 8),
                        ) {
                            if let (Ok(cam_x), Ok(cam_y)) =
                                (read_f64_le(&x_bytes, 0), read_f64_le(&y_bytes, 0))
                            {
                                if cam_x.is_finite() && cam_y.is_finite() {
                                    let dx = hero_x - cam_x;
                                    let dy = hero_y - cam_y;
                                    if dx.hypot(dy) >= 0.25 {
                                        // Match hero rotation_z convention (atan2-style yaw).
                                        return wrap_angle_rad(dy.atan2(dx));
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Fall back to BaseCamera.curDirection / direction (radians, possibly unwrapped).
            for field_offset in [
                root.camera_cur_direction_offset,
                root.camera_direction_offset,
            ] {
                let Ok(yaw_bytes) = read_process_bytes(process, camera + field_offset, 8) else {
                    continue;
                };
                let Ok(yaw) = read_f64_le(&yaw_bytes, 0) else {
                    continue;
                };
                if yaw.is_finite() {
                    return wrap_angle_rad(yaw);
                }
            }
        }
        f64::NAN
    }

    fn read_bounded_utf16(
        process: &OwnedHandle,
        pointer: usize,
        label: &str,
    ) -> Result<String, String> {
        if pointer == 0 {
            return Ok(String::new());
        }
        let bytes = read_process_bytes(process, pointer, 256)?;
        let mut units = Vec::with_capacity(128);
        for pair in bytes.chunks_exact(2) {
            let unit = u16::from_le_bytes([pair[0], pair[1]]);
            if unit == 0 {
                return String::from_utf16(&units)
                    .map_err(|_| format!("{label} is not valid UTF-16"));
            }
            units.push(unit);
        }
        Err(format!("{label} exceeds the bounded string read"))
    }

    struct VirtualField {
        name: String,
        kind: u32,
        value_ptr: usize,
    }

    /// Decode an HVIRTUAL structural value's inline field table.
    /// Soft-fails with an empty vec when the object is not a live virtual.
    fn read_virtual_fields(
        process: &OwnedHandle,
        vobj: usize,
    ) -> Result<Vec<VirtualField>, String> {
        if vobj == 0 {
            return Ok(Vec::new());
        }
        let type_address = read_u64_le(&read_process_bytes(process, vobj, 8)?, 0)? as usize;
        if type_address == 0 {
            return Ok(Vec::new());
        }
        let type_kind =
            read_u32_le(&read_process_bytes(process, type_address, 4)?, 0)?;
        if type_kind != HL_TYPE_KIND_VIRTUAL {
            return Ok(Vec::new());
        }
        let tv = read_u64_le(
            &read_process_bytes(process, type_address + 8, 8)?,
            0,
        )? as usize;
        if tv == 0 {
            return Ok(Vec::new());
        }
        let fields = read_u64_le(
            &read_process_bytes(process, tv + HL_VTYPE_FIELDS_OFFSET, 8)?,
            0,
        )? as usize;
        let nfields = i32::from_le_bytes(
            read_process_bytes(process, tv + HL_VTYPE_NFIELDS_OFFSET, 4)?
                .try_into()
                .unwrap(),
        );
        if fields == 0 || !(1..=64).contains(&nfields) {
            return Ok(Vec::new());
        }
        let mut out = Vec::with_capacity(nfields as usize);
        for index in 0..nfields as usize {
            let field = fields
                .checked_add(index * HL_VFIELD_STRIDE)
                .ok_or_else(|| "HVIRTUAL field address overflowed".to_owned())?;
            let name_ptr = read_u64_le(
                &read_process_bytes(process, field + HL_VFIELD_NAME_OFFSET, 8)?,
                0,
            )? as usize;
            let field_type = read_u64_le(
                &read_process_bytes(process, field + HL_VFIELD_TYPE_OFFSET, 8)?,
                0,
            )? as usize;
            let kind = if field_type == 0 {
                0
            } else {
                read_u32_le(&read_process_bytes(process, field_type, 4)?, 0).unwrap_or(0)
            };
            let value_ptr = read_u64_le(
                &read_process_bytes(
                    process,
                    vobj + HL_VVIRTUAL_DATA_OFFSET + index * 8,
                    8,
                )?,
                0,
            )? as usize;
            let name = if name_ptr == 0 {
                String::new()
            } else {
                let bytes = read_process_bytes_partial(process, name_ptr, 64).unwrap_or_default();
                decode_utf16_z(&bytes, "HVIRTUAL field name")
                    .ok()
                    .flatten()
                    .unwrap_or_default()
            };
            out.push(VirtualField {
                name,
                kind,
                value_ptr,
            });
        }
        Ok(out)
    }

    fn decode_currency_kind_string(
        process: &OwnedHandle,
        code: &CodeAnchor,
        string_obj: usize,
    ) -> Option<String> {
        if string_obj == 0 {
            return None;
        }
        if let Ok(value) =
            read_hashlink_string(process, code.types_address, string_obj, "currency kind")
        {
            if !value.is_empty() {
                return Some(value);
            }
        }
        if let Ok(value) = read_hashlink_identifier(
            process,
            code.types_address,
            string_obj,
            "currency kind id",
        ) {
            if !value.is_empty() {
                return Some(value);
            }
        }
        None
    }

    fn decode_currency_entry(
        process: &OwnedHandle,
        code: &CodeAnchor,
        elem: usize,
    ) -> Option<CurrencySample> {
        if elem == 0 {
            return None;
        }
        // Loadout purse rows are hxbit.ObjProxy { amount:I32, kind:String }.
        // HeroData purse rows (when present) are HVIRTUAL with the same names.
        let type_address = object_type_address(process, elem)?;
        let type_kind =
            read_u32_le(&read_process_bytes(process, type_address, 4).ok()?, 0).ok()?;
        if type_kind == HL_TYPE_KIND_OBJ {
            // ObjProxy_Oamount_Int_kind_*: amount@2, kind@3 (after obj/bit).
            let amount_off = object_field_offset(process, type_address, 2).ok()?;
            let kind_off = object_field_offset(process, type_address, 3).ok()?;
            let amount = i32::from_le_bytes(
                read_process_bytes(process, elem + amount_off, 4)
                    .ok()?
                    .try_into()
                    .ok()?,
            ) as i64;
            let kind_obj =
                read_object_pointer_field(process, elem, kind_off).ok()?;
            let kind = decode_currency_kind_string(process, code, kind_obj)?;
            return Some(CurrencySample { kind, amount });
        }

        let fields = read_virtual_fields(process, elem).ok()?;
        if fields.is_empty() {
            return None;
        }
        let mut kind = String::new();
        let mut amount: Option<i64> = None;
        for field in fields {
            if field.value_ptr == 0 || field.name.is_empty() {
                continue;
            }
            let name = field.name.as_str();
            if matches!(name, "kind" | "id" | "item" | "currency") {
                let Ok(string_obj) = read_u64_le(
                    &read_process_bytes(process, field.value_ptr, 8).unwrap_or_default(),
                    0,
                )
                .map(|value| value as usize) else {
                    continue;
                };
                if let Some(value) = decode_currency_kind_string(process, code, string_obj) {
                    kind = value;
                }
            } else if matches!(name, "amount" | "count" | "value" | "nb") {
                if field.kind == HL_TYPE_KIND_I32 || field.kind == 0 {
                    if let Ok(bytes) = read_process_bytes(process, field.value_ptr, 4) {
                        amount =
                            Some(i32::from_le_bytes(bytes.try_into().unwrap_or([0; 4])) as i64);
                    }
                } else if field.kind == HL_TYPE_KIND_F64 {
                    if let Ok(bytes) = read_process_bytes(process, field.value_ptr, 8) {
                        if let Ok(value) = read_f64_le(&bytes, 0) {
                            if value.is_finite() {
                                amount = Some(value as i64);
                            }
                        }
                    }
                }
            }
        }
        if kind.is_empty() {
            None
        } else {
            Some(CurrencySample {
                kind,
                amount: amount.unwrap_or(0),
            })
        }
    }

    fn object_type_address(process: &OwnedHandle, object: usize) -> Option<usize> {
        if object == 0 {
            return None;
        }
        read_u64_le(
            &read_process_bytes(process, object, 8).unwrap_or_default(),
            0,
        )
        .ok()
        .map(|value| value as usize)
    }

    fn find_hero_data_on_player(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
    ) -> Option<usize> {
        if player == 0 {
            return None;
        }
        let expected_hd = code.types_address + HERO_DATA_TYPE_INDEX * 32;
        for &offset in &[root.player_hero_data_offset, 0xe8usize] {
            let Ok(candidate) = read_object_pointer_field(process, player, offset) else {
                continue;
            };
            if candidate != 0 && object_type_address(process, candidate) == Some(expected_hd) {
                return Some(candidate);
            }
        }
        None
    }

    /// Resolve ArrayObj / ArrayProxyData / ArrayDyn down to an ArrayObj pointer.
    fn resolve_currency_array_obj(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        value: usize,
    ) -> Option<usize> {
        if value == 0 {
            return None;
        }
        let expected_array = code.types_address + ARRAY_OBJ_TYPE_INDEX * 32;
        let expected_proxy = code.types_address + ARRAY_PROXY_TYPE_INDEX * 32;
        let expected_dyn = code.types_address + ARRAY_DYN_TYPE_INDEX * 32;
        let mut current = value;
        let mut current_ty = object_type_address(process, current)?;
        if current_ty == expected_array {
            return Some(current);
        }
        if current_ty == expected_proxy {
            current =
                read_object_pointer_field(process, current, root.array_proxy_array_offset).ok()?;
            current_ty = object_type_address(process, current)?;
        }
        if current_ty == expected_dyn {
            current =
                read_object_pointer_field(process, current, root.array_dyn_array_offset).ok()?;
            current_ty = object_type_address(process, current)?;
        }
        (current_ty == expected_array).then_some(current)
    }

    fn decode_currency_array_obj(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        array: usize,
    ) -> Vec<CurrencySample> {
        let length_candidates = [root.array_length_offset, 0x08usize];
        let storage_candidates = [root.array_storage_offset, 0x10usize];
        for &length_off in &length_candidates {
            let Ok(length_bytes) = read_process_bytes(process, array + length_off, 4) else {
                continue;
            };
            let length = i32::from_le_bytes(length_bytes.try_into().unwrap_or([0; 4]));
            if !(1..=256).contains(&length) {
                continue;
            }
            for &storage_off in &storage_candidates {
                let Ok(storage) = read_object_pointer_field(process, array, storage_off) else {
                    continue;
                };
                if storage == 0 {
                    continue;
                }
                let mut out = Vec::new();
                for index in 0..length as usize {
                    let Some(entry_addr) = storage.checked_add(24 + index * 8) else {
                        break;
                    };
                    let Ok(elem_bytes) = read_process_bytes(process, entry_addr, 8) else {
                        continue;
                    };
                    let Ok(elem) = read_u64_le(&elem_bytes, 0).map(|value| value as usize) else {
                        continue;
                    };
                    if let Some(sample) = decode_currency_entry(process, code, elem) {
                        out.push(sample);
                    }
                }
                if !out.is_empty() {
                    return out;
                }
            }
        }
        Vec::new()
    }

    fn read_currencies_from_array_field(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        owner: usize,
        field_offset: usize,
    ) -> Vec<CurrencySample> {
        let Ok(value) = read_object_pointer_field(process, owner, field_offset) else {
            return Vec::new();
        };
        let Some(array) = resolve_currency_array_obj(process, code, root, value) else {
            return Vec::new();
        };
        decode_currency_array_obj(process, code, root, array)
    }

    /// Purse currencies from `ent.Hero.loadout.currencies` (ArrayProxy of ObjProxy
    /// rows), falling back to `st.player.HeroData.currencies` when present.
    /// Soft-fails to an empty list — never fails the whole telemetry sample.
    fn read_currencies(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
        hero: usize,
    ) -> Vec<CurrencySample> {
        // Primary: live purse on the hero loadout (HeroData is often null client-side).
        if hero != 0 {
            if let Ok(loadout) = read_object_pointer_field(process, hero, root.hero_loadout_offset)
            {
                if loadout != 0
                    && object_type_address(process, loadout)
                        == Some(code.types_address + LOADOUT_TYPE_INDEX * 32)
                {
                    let out = read_currencies_from_array_field(
                        process,
                        code,
                        root,
                        loadout,
                        root.loadout_currencies_offset,
                    );
                    if !out.is_empty() {
                        return out;
                    }
                }
            }
        }

        // Fallback: Player.heroData.currencies when the DB blob is live.
        if let Some(hero_data) = find_hero_data_on_player(process, code, root, player) {
            let out = read_currencies_from_array_field(
                process,
                code,
                root,
                hero_data,
                root.hero_data_currencies_offset,
            );
            if !out.is_empty() {
                return out;
            }
            if root.hero_data_currencies_offset != 0x110 {
                return read_currencies_from_array_field(process, code, root, hero_data, 0x110);
            }
        }
        Vec::new()
    }

    fn read_player_progress(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
    ) -> Option<usize> {
        let hero_data =
            read_object_pointer_field(process, player, root.player_hero_data_offset).ok()?;
        let progress = if hero_data != 0
            && object_type_address(process, hero_data)
                == Some(code.types_address + HERO_DATA_TYPE_INDEX * 32)
        {
            read_object_pointer_field(process, hero_data, root.hero_data_progress_offset).ok()?
        } else {
            read_object_pointer_field(process, player, root.player_progress_offset).ok()?
        };
        if progress == 0 {
            return None;
        }
        if object_type_address(process, progress)
            != Some(code.types_address + PROGRESS_TYPE_INDEX * 32)
        {
            return None;
        }
        Some(progress)
    }

    /// Soft-fail lookup of Progress.counters[key] as a boxed/plain i32.
    fn read_progress_counter(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
        key: &str,
    ) -> Option<i64> {
        let progress = read_player_progress(process, code, root, player)?;
        let counters =
            read_object_pointer_field(process, progress, root.progress_counters_offset).ok()?;
        if counters == 0
            || object_type_address(process, counters)
                != Some(code.types_address + STRING_MAP_TYPE_INDEX * 32)
        {
            return None;
        }
        let handle =
            read_object_pointer_field(process, counters, root.string_map_handle_offset).ok()?;
        if handle == 0 {
            return None;
        }
        let header = read_process_bytes(process, handle, 64).ok()?;
        let values = read_u64_le(&header, 24).ok()? as usize;
        let nentries = read_u32_le(&header, 52).ok()? as usize;
        let maxentries = read_u32_le(&header, 56).ok()? as usize;
        if nentries > maxentries || maxentries > 100_000 || (maxentries > 0 && values == 0) {
            return None;
        }
        const ENTRY_SIZE: usize = 16;
        const CHUNK_ENTRIES: usize = 4096 / ENTRY_SIZE;
        let mut index = 0usize;
        while index < maxentries {
            let chunk = (maxentries - index).min(CHUNK_ENTRIES);
            let entries =
                read_process_bytes(process, values + index * ENTRY_SIZE, chunk * ENTRY_SIZE).ok()?;
            for local in 0..chunk {
                let offset = local * ENTRY_SIZE;
                let key_pointer = read_u64_le(&entries, offset).ok()? as usize;
                let value_pointer = read_u64_le(&entries, offset + 8).ok()? as usize;
                if key_pointer == 0 || value_pointer == 0 {
                    continue;
                }
                let Ok(name) = read_bounded_utf16(process, key_pointer, "progress counter") else {
                    continue;
                };
                let name = if name == key {
                    name
                } else if let Ok(string_name) =
                    read_hashlink_string(process, code.types_address, key_pointer, "progress counter")
                {
                    string_name
                } else {
                    name
                };
                if name != key {
                    continue;
                }
                // Counters are typically boxed i32 (vdynamic): type @0, payload @8.
                let value_type = object_type_address(process, value_pointer)?;
                let kind =
                    read_u32_le(&read_process_bytes(process, value_type, 4).ok()?, 0).ok()?;
                if kind == HL_TYPE_KIND_I32 {
                    let bytes = read_process_bytes(process, value_pointer + 8, 4).ok()?;
                    return Some(i32::from_le_bytes(bytes.try_into().ok()?) as i64);
                }
                // Fallback: plain i32 object field / direct payload.
                if let Ok(bytes) = read_process_bytes(process, value_pointer + 8, 4) {
                    return Some(i32::from_le_bytes(bytes.try_into().ok()?) as i64);
                }
                return None;
            }
            index += chunk;
        }
        None
    }

    fn read_currency_counters(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
    ) -> Vec<(String, i64)> {
        // Only the counters needed for live currency caps.
        const KEYS: &[&str] = &["DemonicSouls_CapacityIndex"];
        let mut out = Vec::new();
        for key in KEYS {
            if let Some(value) = read_progress_counter(process, code, root, player, key) {
                if (0..32).contains(&value) {
                    out.push(((*key).to_owned(), value));
                }
            }
        }
        out
    }

    fn read_completed_elements(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
    ) -> Result<Vec<String>, String> {
        let hero_data = read_object_pointer_field(process, player, root.player_hero_data_offset)?;
        let progress = if hero_data != 0
            && read_u64_le(&read_process_bytes(process, hero_data, 8)?, 0)? as usize
                == code.types_address + HERO_DATA_TYPE_INDEX * 32
        {
            read_object_pointer_field(process, hero_data, root.hero_data_progress_offset)?
        } else {
            read_object_pointer_field(process, player, root.player_progress_offset)?
        };
        if progress == 0 {
            return Ok(Vec::new());
        }
        if read_u64_le(&read_process_bytes(process, progress, 8)?, 0)? as usize
            != code.types_address + PROGRESS_TYPE_INDEX * 32
        {
            return Err("Player.progress is not a live st.player.Progress object".to_owned());
        }
        let elements = read_object_pointer_field(process, progress, root.progress_elements_offset)?;
        if elements == 0 {
            return Ok(Vec::new());
        }
        if read_u64_le(&read_process_bytes(process, elements, 8)?, 0)? as usize
            != code.types_address + MAP_DATA_TYPE_INDEX * 32
        {
            return Err("Progress.elements is not an hxbit.MapData object".to_owned());
        }
        let map_value = read_object_pointer_field(process, elements, root.map_data_map_offset)?;
        if map_value == 0 {
            return Ok(Vec::new());
        }
        let expected_map_type = code.types_address + STRING_MAP_TYPE_INDEX * 32;
        let map_object = if read_u64_le(&read_process_bytes(process, map_value, 8)?, 0)? as usize
            == expected_map_type
        {
            map_value
        } else {
            let wrapper = read_process_bytes(process, map_value, 40)?;
            [8_usize, 16, 24, 32]
                .into_iter()
                .filter_map(|offset| read_u64_le(&wrapper, offset).ok())
                .map(|value| value as usize)
                .find(|candidate| {
                    *candidate != 0
                        && read_process_bytes(process, *candidate, 8)
                            .ok()
                            .and_then(|bytes| read_u64_le(&bytes, 0).ok())
                            .map(|value| value as usize == expected_map_type)
                            .unwrap_or(false)
                })
                .ok_or_else(|| "Progress.elements map is not a StringMap".to_owned())?
        };
        let handle = read_object_pointer_field(process, map_object, root.string_map_handle_offset)?;
        if handle == 0 {
            return Ok(Vec::new());
        }
        let header = read_process_bytes(process, handle, 64)?;
        let values = read_u64_le(&header, 24)? as usize;
        let nentries = read_u32_le(&header, 52)? as usize;
        let maxentries = read_u32_le(&header, 56)? as usize;
        if nentries > maxentries || maxentries > 100_000 || (maxentries > 0 && values == 0) {
            return Err("Progress.elements StringMap header failed sanity validation".to_owned());
        }
        // Process reads are capped at 4096 bytes; walk the map in chunks.
        const ENTRY_SIZE: usize = 16;
        const CHUNK_ENTRIES: usize = 4096 / ENTRY_SIZE;
        let expected_value_type = code.types_address + COMPLETION_PROXY_TYPE_INDEX * 32;
        let mut completed = Vec::new();
        let mut index = 0usize;
        while index < maxentries {
            let chunk = (maxentries - index).min(CHUNK_ENTRIES);
            let entries =
                read_process_bytes(process, values + index * ENTRY_SIZE, chunk * ENTRY_SIZE)?;
            for local in 0..chunk {
                let offset = local * ENTRY_SIZE;
                let key_pointer = read_u64_le(&entries, offset)? as usize;
                let value_pointer = read_u64_le(&entries, offset + 8)? as usize;
                if key_pointer == 0 || value_pointer == 0 {
                    continue;
                }
                let value_type =
                    read_u64_le(&read_process_bytes(process, value_pointer, 8)?, 0)? as usize;
                if value_type != expected_value_type {
                    continue;
                }
                let value = read_f64_le(
                    &read_process_bytes(
                        process,
                        value_pointer + root.completion_proxy_completed_offset,
                        8,
                    )?,
                    0,
                )?;
                if value >= 1.0 {
                    let key = read_bounded_utf16(process, key_pointer, "completed element key")?;
                    if !key.is_empty() {
                        completed.push(key);
                    }
                }
            }
            index += chunk;
        }
        completed.sort_unstable();
        completed.dedup();
        Ok(completed)
    }

    fn read_group_players(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        player: usize,
    ) -> Result<Vec<usize>, String> {
        let group = read_object_pointer_field(process, player, root.player_group_offset)?;
        if group == 0 {
            return Ok(Vec::new());
        }
        if read_u64_le(&read_process_bytes(process, group, 8)?, 0)? as usize
            != code.types_address + GROUP_TYPE_INDEX * 32
        {
            return Err("Player.group is not a live st.Group object".to_owned());
        }
        let proxy = read_object_pointer_field(process, group, root.group_players_offset)?;
        if proxy == 0 {
            return Ok(Vec::new());
        }
        if read_u64_le(&read_process_bytes(process, proxy, 8)?, 0)? as usize
            != code.types_address + ARRAY_PROXY_TYPE_INDEX * 32
        {
            return Err("Group.players is not an ArrayProxyData object".to_owned());
        }
        let dynamic_array =
            read_object_pointer_field(process, proxy, root.array_proxy_array_offset)?;
        if dynamic_array == 0 {
            return Ok(Vec::new());
        }
        if read_u64_le(&read_process_bytes(process, dynamic_array, 8)?, 0)? as usize
            != code.types_address + ARRAY_DYN_TYPE_INDEX * 32
        {
            return Err("Group.players proxy does not contain an ArrayDyn".to_owned());
        }
        let array = read_object_pointer_field(process, dynamic_array, root.array_dyn_array_offset)?;
        if array == 0 {
            return Ok(Vec::new());
        }
        if read_u64_le(&read_process_bytes(process, array, 8)?, 0)? as usize
            != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32
        {
            return Err("Group.players ArrayDyn does not contain an ArrayObj".to_owned());
        }
        let length = read_u32_le(
            &read_process_bytes(process, array + root.array_length_offset, 4)?,
            0,
        )? as usize;
        if length > 16 {
            return Err("Group player count exceeded its safety bound".to_owned());
        }
        if length == 0 {
            return Ok(Vec::new());
        }
        let storage = read_object_pointer_field(process, array, root.array_storage_offset)?;
        if storage == 0 {
            return Ok(Vec::new());
        }
        let header = read_process_bytes(process, storage, 24)?;
        let storage_length = read_u32_le(&header, 16)? as usize;
        if storage_length < length || storage_length > 64 {
            return Err("Group player array storage failed validation".to_owned());
        }
        let entries = read_process_bytes(process, storage + 24, length * 8)?;
        let mut players = Vec::new();
        for index in 0..length {
            let candidate = read_u64_le(&entries, index * 8)? as usize;
            if candidate != 0
                && read_u64_le(&read_process_bytes(process, candidate, 8)?, 0)? as usize
                    == code.types_address + PLAYER_TYPE_INDEX * 32
            {
                players.push(candidate);
            }
        }
        Ok(players)
    }

    fn read_int_map_f64(
        process: &OwnedHandle,
        types_address: usize,
        map_address: usize,
        key: i32,
    ) -> Result<Option<f64>, String> {
        if map_address == 0 {
            return Ok(None);
        }
        // HashLink's official hl_hi_map layout (src/std/maps.h): cells,
        // nexts, entries, values, free-list, then counts. Iterating the
        // bounded entry/value arrays is safer here than reproducing hashing.
        let header = read_process_bytes(process, map_address, 64)?;
        let entries_address = read_u64_le(&header, 16)? as usize;
        let values_address = read_u64_le(&header, 24)? as usize;
        let nentries = read_u32_le(&header, 52)? as usize;
        let maxentries = read_u32_le(&header, 56)? as usize;
        if nentries > maxentries || maxentries > 512 {
            return Err(format!(
                "HashLink IntMap header mismatch at 0x{map_address:x}: q0=0x{:x}, q1=0x{:x}, q2=0x{:x}, q3=0x{:x}, u48={}, u52={}, u56={}, u60={}",
                read_u64_le(&header, 0)?,
                read_u64_le(&header, 8)?,
                read_u64_le(&header, 16)?,
                read_u64_le(&header, 24)?,
                read_u32_le(&header, 48)?,
                read_u32_le(&header, 52)?,
                read_u32_le(&header, 56)?,
                read_u32_le(&header, 60)?,
            ));
        }
        if maxentries == 0 || entries_address == 0 || values_address == 0 {
            return Ok(None);
        }
        let entries = read_process_bytes(process, entries_address, maxentries * 4)?;
        let values = read_process_bytes(process, values_address, maxentries * 8)?;
        for index in 0..maxentries {
            let entry_key =
                i32::from_le_bytes(entries[index * 4..index * 4 + 4].try_into().unwrap());
            if entry_key != key {
                continue;
            }
            let value_address = read_u64_le(&values, index * 8)? as usize;
            if value_address == 0 {
                continue;
            }
            let value = read_process_bytes(process, value_address, 16)?;
            let value_type = read_u64_le(&value, 0)? as usize;
            if value_type != types_address + 6 * 32 {
                return Err("HashLink IntMap health maximum is not an f64".to_owned());
            }
            return Ok(Some(read_f64_le(&value, 8)?));
        }
        Ok(None)
    }

    fn find_shield_gauge(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        gauge: usize,
    ) -> Result<Option<usize>, String> {
        let mut current = gauge;
        for _ in 0..8 {
            current = match read_object_pointer_field(process, current, root.h2d_parent_offset) {
                Ok(value) if value != 0 => value,
                _ => return Ok(None),
            };
            let current_type = read_u64_le(&read_process_bytes(process, current, 8)?, 0)? as usize;
            if current_type != code.types_address + HEALTH_BAR_TYPE_INDEX * 32 {
                continue;
            }
            let shield =
                read_object_pointer_field(process, current, root.health_bar_shield_gauge_offset)?;
            if shield != 0
                && read_u64_le(&read_process_bytes(process, shield, 8)?, 0)? as usize
                    == code.types_address + 4_672 * 32
            {
                return Ok(Some(shield));
            }
            return Ok(None);
        }
        Ok(None)
    }

    fn read_hud_max_health(
        process: &OwnedHandle,
        code: &CodeAnchor,
        root: &PlayerRoot,
        game_app: usize,
        hero: usize,
    ) -> Result<Option<(usize, Option<usize>, f64)>, String> {
        let gui = read_object_pointer_field(process, game_app, root.gui_offset)?;
        if gui == 0 {
            return Ok(None);
        }
        let gui_type = read_u64_le(&read_process_bytes(process, gui, 8)?, 0)? as usize;
        if gui_type != code.types_address + GAME_UI_TYPE_INDEX * 32 {
            return Ok(None);
        }
        let widgets = read_object_pointer_field(process, gui, root.widgets_offset)?;
        if widgets == 0 {
            return Ok(None);
        }
        let widgets_type = read_u64_le(&read_process_bytes(process, widgets, 8)?, 0)? as usize;
        if widgets_type != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32 {
            return Ok(None);
        }
        let length_bytes = read_process_bytes(process, widgets + root.array_length_offset, 4)?;
        let length = read_u32_le(&length_bytes, 0)? as usize;
        if length > 256 {
            return Err("BaseUI widget list exceeded its safety bound".to_owned());
        }
        let storage = read_object_pointer_field(process, widgets, root.array_storage_offset)?;
        if storage == 0 || length == 0 {
            return Ok(None);
        }
        // HashLink varray: element type, array type, size, pad, then inline data.
        let storage_header = read_process_bytes(process, storage, 24)?;
        let storage_length = read_u32_le(&storage_header, 16)? as usize;
        if storage_length < length || storage_length > 4_096 {
            return Ok(None);
        }
        let entries = read_process_bytes(process, storage + 24, length * 8)?;
        let mut pending = Vec::new();
        for index in 0..length {
            let dynamic = read_u64_le(&entries, index * 8)? as usize;
            if dynamic == 0 {
                continue;
            }
            let dynamic_value = match read_process_bytes(process, dynamic, 8) {
                Ok(bytes) => bytes,
                Err(_) => continue,
            };
            let widget_type = read_u64_le(&dynamic_value, 0)? as usize;
            if widget_type != code.types_address + 1_209 * 32 {
                continue;
            }
            let widget = dynamic;
            let container =
                read_object_pointer_field(process, widget, root.widget_container_offset)?;
            if container != 0 {
                pending.push((container, 0_usize));
            }
        }
        // LIFO traversal: append the persistent HUD last so it is searched
        // before generic world widgets.
        let game_root = read_object_pointer_field(process, gui, root.game_ui_game_root_offset)?;
        if game_root != 0
            && read_u64_le(&read_process_bytes(process, game_root, 8)?, 0)? as usize
                == code.types_address + GAME_UI_ROOT_TYPE_INDEX * 32
        {
            let hud = read_object_pointer_field(process, game_root, root.game_ui_root_hud_offset)?;
            if hud != 0
                && read_u64_le(&read_process_bytes(process, hud, 8)?, 0)? as usize
                    == code.types_address + 1_328 * 32
            {
                pending.push((hud, 0_usize));
            }
        }

        let mut visited = Vec::new();
        while let Some((widget, depth)) = pending.pop() {
            if depth > 64 || visited.len() >= 8_192 || visited.contains(&widget) {
                continue;
            }
            visited.push(widget);
            let widget_type = match read_process_bytes(process, widget, 8) {
                Ok(bytes) => read_u64_le(&bytes, 0)? as usize,
                Err(_) => continue,
            };
            if widget_type == code.types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32 {
                let bound_unit =
                    read_object_pointer_field(process, widget, root.attribute_bar_unit_offset)?;
                let attribute_id_pointer =
                    read_object_pointer_field(process, widget, root.attribute_bar_id_offset)?;
                let attribute_id = read_hashlink_string(
                    process,
                    code.types_address,
                    attribute_id_pointer,
                    "HUD attribute id",
                )?;
                let value = read_f64_le(
                    &read_process_bytes(process, widget + root.base_gauge_max_offset, 8)?,
                    0,
                )?;
                if bound_unit == hero
                    && attribute_id == "Health"
                    && value.is_finite()
                    && value > 0.0
                {
                    let shield = find_shield_gauge(process, code, root, widget)?;
                    return Ok(Some((widget, shield, value)));
                }
            }
            if widget_type == code.types_address + HERO_WIDGET_TYPE_INDEX * 32
                && read_object_pointer_field(process, widget, root.hero_widget_hero_offset)? == hero
            {
                let health_bar =
                    read_object_pointer_field(process, widget, root.hero_widget_health_bar_offset)?;
                if health_bar != 0
                    && read_u64_le(&read_process_bytes(process, health_bar, 8)?, 0)? as usize
                        == code.types_address + HEALTH_BAR_TYPE_INDEX * 32
                {
                    let gauge = read_object_pointer_field(
                        process,
                        health_bar,
                        root.health_bar_health_gauge_offset,
                    )?;
                    if gauge != 0
                        && read_u64_le(&read_process_bytes(process, gauge, 8)?, 0)? as usize
                            == code.types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32
                    {
                        let value = read_f64_le(
                            &read_process_bytes(process, gauge + root.base_gauge_max_offset, 8)?,
                            0,
                        )?;
                        if value.is_finite() && value > 0.0 {
                            let shield = read_object_pointer_field(
                                process,
                                health_bar,
                                root.health_bar_shield_gauge_offset,
                            )?;
                            let shield = (shield != 0).then_some(shield);
                            return Ok(Some((gauge, shield, value)));
                        }
                    }
                }
            }

            let children =
                match read_object_pointer_field(process, widget, root.h2d_children_offset) {
                    Ok(value) if value != 0 => value,
                    _ => continue,
                };
            let children_type = match read_process_bytes(process, children, 8) {
                Ok(bytes) => read_u64_le(&bytes, 0)? as usize,
                Err(_) => continue,
            };
            if children_type != code.types_address + ARRAY_OBJ_TYPE_INDEX * 32 {
                continue;
            }
            let child_count = read_u32_le(
                &read_process_bytes(process, children + root.array_length_offset, 4)?,
                0,
            )? as usize;
            if child_count == 0 || child_count > 256 {
                continue;
            }
            let child_storage =
                read_object_pointer_field(process, children, root.array_storage_offset)?;
            if child_storage == 0 {
                continue;
            }
            let child_header = read_process_bytes(process, child_storage, 24)?;
            let child_storage_count = read_u32_le(&child_header, 16)? as usize;
            if child_storage_count < child_count || child_storage_count > 4_096 {
                continue;
            }
            let child_entries = read_process_bytes(process, child_storage + 24, child_count * 8)?;
            for child_index in 0..child_count {
                let dynamic = read_u64_le(&child_entries, child_index * 8)? as usize;
                if dynamic == 0 {
                    continue;
                }
                let dynamic_value = match read_process_bytes(process, dynamic, 8) {
                    Ok(bytes) => bytes,
                    Err(_) => continue,
                };
                let child_type = read_u64_le(&dynamic_value, 0)? as usize;
                if child_type >= code.types_address && (child_type - code.types_address) % 32 == 0 {
                    let child = dynamic;
                    pending.push((child, depth + 1));
                }
            }
        }
        Ok(None)
    }

    fn wide_string(buffer: &[u16]) -> String {
        let end = buffer
            .iter()
            .position(|value| *value == 0)
            .unwrap_or(buffer.len());
        OsString::from_wide(&buffer[..end])
            .to_string_lossy()
            .into_owned()
    }

    fn json_string(value: &str) -> String {
        let mut escaped = String::with_capacity(value.len() + 2);
        escaped.push('"');
        for character in value.chars() {
            match character {
                '"' => escaped.push_str("\\\""),
                '\\' => escaped.push_str("\\\\"),
                '\n' => escaped.push_str("\\n"),
                '\r' => escaped.push_str("\\r"),
                '\t' => escaped.push_str("\\t"),
                value if value.is_control() => {
                    use std::fmt::Write;
                    let _ = write!(escaped, "\\u{:04x}", value as u32);
                }
                value => escaped.push(value),
            }
        }
        escaped.push('"');
        escaped
    }

    struct ExecutableFingerprint {
        machine: u16,
        pe_timestamp: u32,
        image_size: u32,
        file_size: u64,
        crc32: u32,
    }

    struct ModuleInfo {
        name: String,
        path: String,
        base_address: usize,
        size: u32,
    }

    struct BytecodeFingerprint {
        version: u8,
        file_size: u64,
        crc32: u32,
    }

    fn read_u16_le(data: &[u8], offset: usize) -> Result<u16, String> {
        let bytes = data
            .get(offset..offset + 2)
            .ok_or_else(|| format!("PE field at 0x{offset:x} is outside the file"))?;
        Ok(u16::from_le_bytes([bytes[0], bytes[1]]))
    }

    fn read_u32_le(data: &[u8], offset: usize) -> Result<u32, String> {
        let bytes = data
            .get(offset..offset + 4)
            .ok_or_else(|| format!("PE field at 0x{offset:x} is outside the file"))?;
        Ok(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    fn read_u64_le(data: &[u8], offset: usize) -> Result<u64, String> {
        let bytes = data
            .get(offset..offset + 8)
            .ok_or_else(|| "unexpected end of data while reading u64".to_owned())?;
        Ok(u64::from_le_bytes(bytes.try_into().unwrap()))
    }

    fn read_f64_le(data: &[u8], offset: usize) -> Result<f64, String> {
        let bytes = data
            .get(offset..offset + 8)
            .ok_or_else(|| "unexpected end of data while reading f64".to_owned())?;
        Ok(f64::from_le_bytes(bytes.try_into().unwrap()))
    }

    fn crc32(data: &[u8]) -> u32 {
        let mut crc = u32::MAX;
        for byte in data {
            crc ^= u32::from(*byte);
            for _ in 0..8 {
                let polynomial = if crc & 1 != 0 { 0xedb8_8320 } else { 0 };
                crc = (crc >> 1) ^ polynomial;
            }
        }
        !crc
    }

    fn fingerprint_executable(path: &str) -> Result<ExecutableFingerprint, String> {
        let data = std::fs::read(path)
            .map_err(|error| format!("could not read Farever executable: {error}"))?;
        if data.len() < 0x40 || data.get(0..2) != Some(b"MZ") {
            return Err("Farever executable has an invalid DOS header".to_owned());
        }

        let pe_offset = read_u32_le(&data, 0x3c)? as usize;
        if data.get(pe_offset..pe_offset + 4) != Some(b"PE\0\0") {
            return Err("Farever executable has an invalid PE signature".to_owned());
        }

        let optional_header = pe_offset
            .checked_add(24)
            .ok_or_else(|| "Farever PE header offset overflowed".to_owned())?;
        if read_u16_le(&data, optional_header)? != 0x020b {
            return Err("Farever executable is not a 64-bit PE image".to_owned());
        }

        Ok(ExecutableFingerprint {
            machine: read_u16_le(&data, pe_offset + 4)?,
            pe_timestamp: read_u32_le(&data, pe_offset + 8)?,
            image_size: read_u32_le(&data, optional_header + 56)?,
            file_size: data.len() as u64,
            crc32: crc32(&data),
        })
    }

    fn fingerprint_bytecode(path: &str) -> Result<BytecodeFingerprint, String> {
        let data = std::fs::read(path)
            .map_err(|error| format!("could not read Farever HashLink bytecode: {error}"))?;
        if data.get(0..3) != Some(b"HLB") {
            return Err("Farever hlboot.dat has an invalid HashLink header".to_owned());
        }
        let version = *data
            .get(3)
            .ok_or_else(|| "Farever hlboot.dat has a truncated header".to_owned())?;
        Ok(BytecodeFingerprint {
            version,
            file_size: data.len() as u64,
            crc32: crc32(&data),
        })
    }

    fn matches_supported_profile(fingerprint: &ExecutableFingerprint) -> bool {
        fingerprint.machine == SUPPORTED_MACHINE
            && fingerprint.pe_timestamp == SUPPORTED_PE_TIMESTAMP
            && fingerprint.image_size == SUPPORTED_IMAGE_SIZE
            && fingerprint.file_size == SUPPORTED_FILE_SIZE
            && fingerprint.crc32 == SUPPORTED_CRC32
    }

    fn find_farever_process() -> Result<Dword, String> {
        let snapshot = OwnedHandle::new(unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) })
            .ok_or_else(|| format!("process snapshot failed (Win32 error {})", last_error()))?;

        let mut entry: ProcessEntry32W = unsafe { zeroed() };
        entry.dw_size = size_of::<ProcessEntry32W>() as Dword;

        if unsafe { Process32FirstW(snapshot.raw(), &mut entry) } == FALSE {
            return Err(format!(
                "process enumeration failed (Win32 error {})",
                last_error()
            ));
        }

        loop {
            if wide_string(&entry.exe_file).eq_ignore_ascii_case("Farever.exe") {
                return Ok(entry.process_id);
            }
            if unsafe { Process32NextW(snapshot.raw(), &mut entry) } == FALSE {
                break;
            }
        }

        Err("Farever.exe is not running".to_owned())
    }

    fn loaded_modules(process_id: Dword) -> Result<Vec<ModuleInfo>, String> {
        let snapshot = OwnedHandle::new(unsafe {
            CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, process_id)
        })
        .ok_or_else(|| format!("module snapshot failed (Win32 error {})", last_error()))?;

        let mut entry: ModuleEntry32W = unsafe { zeroed() };
        entry.dw_size = size_of::<ModuleEntry32W>() as Dword;
        if unsafe { Module32FirstW(snapshot.raw(), &mut entry) } == FALSE {
            return Err(format!(
                "module enumeration failed (Win32 error {})",
                last_error()
            ));
        }

        let mut modules = Vec::new();
        loop {
            modules.push(ModuleInfo {
                name: wide_string(&entry.module_name),
                path: wide_string(&entry.exe_path),
                base_address: entry.base_address as usize,
                size: entry.base_size,
            });
            if unsafe { Module32NextW(snapshot.raw(), &mut entry) } == FALSE {
                break;
            }
        }
        Ok(modules)
    }

    fn parent_path(path: &str) -> &str {
        match path.rfind(['\\', '/']) {
            Some(index) => &path[..index],
            None => "",
        }
    }

    fn module_json(module: &ModuleInfo, application_directory: &str) -> Result<String, String> {
        let is_application_local =
            parent_path(&module.path).eq_ignore_ascii_case(application_directory);
        let fingerprint_json = if is_application_local {
            let fingerprint = fingerprint_executable(&module.path)?;
            format!(
                concat!(
                    "{{",
                    "\"machine\":\"0x{:04x}\",",
                    "\"pe_timestamp\":{},",
                    "\"image_size\":{},",
                    "\"file_size\":{},",
                    "\"crc32\":\"{:08x}\"",
                    "}}"
                ),
                fingerprint.machine,
                fingerprint.pe_timestamp,
                fingerprint.image_size,
                fingerprint.file_size,
                fingerprint.crc32
            )
        } else {
            "null".to_owned()
        };

        Ok(format!(
            concat!(
                "{{",
                "\"name\":{},",
                "\"path\":{},",
                "\"base_address\":\"0x{:x}\",",
                "\"size\":{},",
                "\"application_local\":{},",
                "\"fingerprint\":{}",
                "}}"
            ),
            json_string(&module.name),
            json_string(&module.path),
            module.base_address,
            module.size,
            is_application_local,
            fingerprint_json
        ))
    }

    fn attach_for_watch() -> Result<(OwnedHandle, CodeAnchor), String> {
        let process_id = find_farever_process()?;
        let process =
            OwnedHandle::new(unsafe { OpenProcess(FAREVER_READ_ACCESS, FALSE, process_id) })
                .ok_or_else(|| {
                    format!(
                        "opening Farever.exe read-only failed (Win32 error {})",
                        last_error()
                    )
                })?;
        let modules = loaded_modules(process_id)?;
        let farever = modules
            .iter()
            .find(|module| module.name.eq_ignore_ascii_case("Farever.exe"))
            .ok_or_else(|| "Farever.exe main module was not found".to_owned())?;
        let libhl = modules
            .iter()
            .find(|module| module.name.eq_ignore_ascii_case("libhl.dll"))
            .ok_or_else(|| "libhl.dll was not found in the Farever process".to_owned())?;
        let fingerprint = fingerprint_executable(&farever.path)?;
        if farever.size != fingerprint.image_size || !matches_supported_profile(&fingerprint) {
            return Err("Farever build is not supported for live telemetry".to_owned());
        }
        verify_live_pe_header(&process, farever)?;
        verify_live_pe_header(&process, libhl)?;
        let hlboot_path = format!("{}\\hlboot.dat", parent_path(&farever.path));
        let hlboot = fingerprint_bytecode(&hlboot_path)?;
        if hlboot.version != SUPPORTED_HLBOOT_VERSION
            || hlboot.file_size != SUPPORTED_HLBOOT_FILE_SIZE
            || hlboot.crc32 != SUPPORTED_HLBOOT_CRC32
        {
            return Err("Farever hlboot.dat is not supported for live telemetry".to_owned());
        }
        let runtime = read_runtime_anchor(&process, farever)?;
        // Watch mode attaches as soon as HashLink is up, even before the
        // player has entered a world (GameApp/player/hero may still be null).
        let code = read_code_anchor(&process, &runtime, false)?;
        Ok((process, code))
    }

    fn waiting_report(sequence: u64, timestamp_ms: u128, message: &str) -> String {
        format!(
            "{{\"schema\":1,\"bridge_version\":\"0.23.6\",\"state\":\"waiting\",\"sequence\":{sequence},\"timestamp_ms\":{timestamp_ms},\"message\":{}}}\n",
            json_string(message)
        )
    }

    /// Sample-time failures that are expected during loading / teleport / GC.
    /// Keep the CodeAnchor and retry instead of tearing down the attach.
    fn is_transient_sample_error(error: &str) -> bool {
        error.contains("temporarily unavailable")
            || error.contains("type mismatch")
            || error.contains("process read")
            || error.contains("Win32 error")
            || error.contains("partial")
            || error.contains("null")
            || error.contains("not a HashLink")
            || error.contains("failed sanity")
            || error.contains("exceeded its safety bound")
            || error.contains("invalid length")
    }

    /// Only drop the process handle for hard attach problems (or after a
    /// prolonged streak of transient sample failures — handled by the watch loop).
    fn should_reattach(error: &str) -> bool {
        error.contains("Farever.exe is not running")
            || error.contains("main module was not found")
            || error.contains("libhl.dll was not found")
            || error.contains("opening Farever.exe")
            || error.contains("code header mismatch")
            || error.contains("hlboot.dat is not supported")
            || error.contains("Farever build is not supported")
            || error.contains("HashLink main context")
    }

    fn sample_party_member(
        process: &OwnedHandle,
        code: &CodeAnchor,
        player: usize,
        local_x: f64,
        local_y: f64,
        local_z: f64,
        allow_hud_discovery: bool,
        gauge_cache: &mut Vec<PartyGaugeCache>,
    ) -> Result<Option<PartySample>, String> {
        let root = &code.player_root;
        let hero = read_object_pointer_field(process, player, root.player_hero_offset)?;
        if hero == 0
            || read_u64_le(&read_process_bytes(process, hero, 8)?, 0)? as usize
                != code.types_address + HERO_TYPE_INDEX * 32
        {
            return Ok(None);
        }
        let name_pointer = read_object_pointer_field(process, player, root.player_name_offset)?;
        let uid_pointer = read_object_pointer_field(process, player, root.player_uid_offset)?;
        let player_name =
            read_hashlink_string(process, code.types_address, name_pointer, "party name")?;
        let uid = read_hashlink_string(process, code.types_address, uid_pointer, "party uid")?;
        let hero_name_pointer = read_object_pointer_field(process, hero, root.hero_name_offset)?;
        let hero_name =
            read_hashlink_string(process, code.types_address, hero_name_pointer, "party hero name")
                .unwrap_or_default();
        let name = pick_player_display_name(&player_name, &hero_name);
        let unit_kind = read_object_pointer_field(process, hero, root.unit_kind_offset)?;
        let class_name =
            read_hashlink_identifier(process, code.types_address, unit_kind, "party unit kind")
                .unwrap_or_default();
        let class_name = if looks_like_element_kind_id(&class_name) {
            String::new()
        } else {
            class_name
        };
        let level = i32::from_le_bytes(
            read_process_bytes(process, hero + root.level_offset, 4)?
                .try_into()
                .unwrap(),
        );
        let connected =
            read_process_bytes(process, player + root.player_connected_offset, 1)?[0] != 0;
        let x = read_f64_le(
            &read_process_bytes(process, hero + root.position_x_offset, 8)?,
            0,
        )?;
        let y = read_f64_le(
            &read_process_bytes(process, hero + root.position_y_offset, 8)?,
            0,
        )?;
        let z = read_f64_le(
            &read_process_bytes(process, hero + root.position_z_offset, 8)?,
            0,
        )?;
        let rotation = read_f64_le(
            &read_process_bytes(process, hero + root.rotation_z_offset, 8)?,
            0,
        )?;
        let attributes = read_object_pointer_field(process, hero, root.attributes_offset)?;
        if attributes == 0
            || read_u64_le(&read_process_bytes(process, attributes, 8)?, 0)? as usize
                != code.types_address + HERO_ATTRIBUTES_TYPE_INDEX * 32
        {
            return Ok(None);
        }
        let health = read_f64_le(
            &read_process_bytes(process, attributes + root.health_offset, 8)?,
            0,
        )?;
        let raw_max_health = read_f64_le(
            &read_process_bytes(process, attributes + root.max_health_offset, 8)?,
            0,
        )?;
        let raw_shield = read_f64_le(
            &read_process_bytes(process, attributes + root.shield_offset, 8)?,
            0,
        )?;
        let cache_index = gauge_cache.iter().position(|entry| entry.hero == hero);
        let mut cached = cache_index
            .map(|index| gauge_cache[index])
            .unwrap_or(PartyGaugeCache {
                hero,
                health: None,
                shield: None,
            });
        let mut max_health = cached.health.and_then(|gauge| {
            let gauge_type = read_process_bytes(process, gauge, 8).ok()?;
            if read_u64_le(&gauge_type, 0).ok()? as usize
                != code.types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32
                || read_object_pointer_field(process, gauge, root.attribute_bar_unit_offset).ok()?
                    != hero
            {
                return None;
            }
            let value = read_f64_le(
                &read_process_bytes(process, gauge + root.base_gauge_max_offset, 8).ok()?,
                0,
            )
            .ok()?;
            (value.is_finite() && value > 0.0).then_some(value)
        });
        if max_health.is_none() && allow_hud_discovery {
            if let Some((health_gauge, shield_gauge, value)) =
                read_hud_max_health(process, code, root, code.player_root.game_app_address, hero)?
            {
                cached.health = Some(health_gauge);
                cached.shield = shield_gauge;
                max_health = Some(value);
            }
        }
        if let Some(index) = cache_index {
            gauge_cache[index] = cached;
        } else {
            gauge_cache.push(cached);
        }
        let max_health = max_health.unwrap_or(raw_max_health);
        let shield = cached
            .shield
            .and_then(|gauge| {
                let gauge_type = read_process_bytes(process, gauge, 8).ok()?;
                if read_u64_le(&gauge_type, 0).ok()? as usize != code.types_address + 4_672 * 32 {
                    return None;
                }
                let visible =
                    read_process_bytes(process, gauge + root.h2d_visible_offset, 1).ok()?[0] != 0;
                let ratio = read_f64_le(
                    &read_process_bytes(process, gauge + root.base_gauge_value_offset, 8).ok()?,
                    0,
                )
                .ok()?;
                (visible && ratio.is_finite() && ratio >= 0.0)
                    .then_some((ratio * max_health).ceil())
            })
            .unwrap_or(raw_shield);
        let dx = x - local_x;
        let dy = y - local_y;
        let dz = z - local_z;
        let distance = (dx * dx + dy * dy + dz * dz).sqrt();
        if !(0..=1_000).contains(&level)
            || [x, y, z, rotation, health, max_health, shield, distance]
                .iter()
                .any(|value| !value.is_finite() || value.abs() > 1_000_000_000.0)
        {
            return Err("Party member telemetry failed sanity validation".to_owned());
        }
        Ok(Some(PartySample {
            name,
            uid,
            class_name,
            level,
            connected,
            health,
            max_health,
            shield,
            x,
            y,
            z,
            rotation,
            distance,
        }))
    }

    fn sample_telemetry(
        process: &OwnedHandle,
        code: &CodeAnchor,
        hud_health_gauge: &mut Option<usize>,
        hud_shield_gauge: &mut Option<usize>,
        allow_hud_discovery: bool,
        party_gauge_cache: &mut Vec<PartyGaugeCache>,
        completed_elements_cache: &mut Vec<String>,
    ) -> Result<TelemetrySample, String> {
        let root = &code.player_root;
        let game_app = read_object_pointer_field(
            process,
            root.app_static_holder_address,
            root.app_instance_offset,
        )?;
        if game_app == 0
            || read_u64_le(&read_process_bytes(process, game_app, 8)?, 0)? as usize
                != code.types_address + GAME_APP_TYPE_INDEX * 32
        {
            return Err("GameApp is temporarily unavailable".to_owned());
        }
        let player = read_object_pointer_field(process, game_app, root.player_offset)?;
        let hero = read_object_pointer_field(process, game_app, root.hero_offset)?;
        if player == 0
            || read_u64_le(&read_process_bytes(process, player, 8)?, 0)? as usize
                != code.types_address + PLAYER_TYPE_INDEX * 32
        {
            return Err("player is temporarily unavailable".to_owned());
        }
        if hero == 0
            || read_u64_le(&read_process_bytes(process, hero, 8)?, 0)? as usize
                != code.types_address + HERO_TYPE_INDEX * 32
        {
            return Err("Hero is temporarily unavailable".to_owned());
        }
        let x = read_f64_le(
            &read_process_bytes(process, hero + root.position_x_offset, 8)?,
            0,
        )?;
        let y = read_f64_le(
            &read_process_bytes(process, hero + root.position_y_offset, 8)?,
            0,
        )?;
        let z = read_f64_le(
            &read_process_bytes(process, hero + root.position_z_offset, 8)?,
            0,
        )?;
        let rotation = read_f64_le(
            &read_process_bytes(process, hero + root.rotation_z_offset, 8)?,
            0,
        )?;
        let name_pointer = read_object_pointer_field(process, player, root.player_name_offset)?;
        let player_name =
            read_hashlink_string(process, code.types_address, name_pointer, "player name")?;
        let uid_pointer = read_object_pointer_field(process, player, root.player_uid_offset)?;
        let uid = read_hashlink_string(process, code.types_address, uid_pointer, "player uid")?;
        let hero_name_pointer = read_object_pointer_field(process, hero, root.hero_name_offset)?;
        let hero_name =
            read_hashlink_string(process, code.types_address, hero_name_pointer, "hero name")
                .unwrap_or_default();
        let name = pick_player_display_name(&player_name, &hero_name);
        let unit_kind = read_object_pointer_field(process, hero, root.unit_kind_offset)?;
        let class_name =
            read_hashlink_identifier(process, code.types_address, unit_kind, "hero unit kind")
                .unwrap_or_default();
        let class_name = if looks_like_element_kind_id(&class_name) {
            String::new()
        } else {
            class_name
        };
        let level = i32::from_le_bytes(
            read_process_bytes(process, hero + root.level_offset, 4)?
                .try_into()
                .unwrap(),
        );
        let in_combat = read_process_bytes(process, hero + root.in_combat_offset, 1)?[0] != 0;
        let attributes = read_object_pointer_field(process, hero, root.attributes_offset)?;
        if attributes == 0 {
            return Err("Hero attributes are temporarily unavailable (null)".to_owned());
        }
        let attributes_type =
            read_u64_le(&read_process_bytes(process, attributes, 8)?, 0)? as usize;
        let expected_attributes_type = code.types_address + HERO_ATTRIBUTES_TYPE_INDEX * 32;
        if attributes_type != expected_attributes_type {
            return Err(format!(
                "Hero attributes type mismatch: object=0x{attributes:x}, expected=0x{expected_attributes_type:x}, actual=0x{attributes_type:x}"
            ));
        }
        let vitality = read_f64_le(
            &read_process_bytes(process, attributes + root.vitality_offset, 8)?,
            0,
        )?;
        let health = read_f64_le(
            &read_process_bytes(process, attributes + root.health_offset, 8)?,
            0,
        )?;
        let raw_max_health = read_f64_le(
            &read_process_bytes(process, attributes + root.max_health_offset, 8)?,
            0,
        )?;
        let resource_max_cache =
            read_object_pointer_field(process, attributes, root.last_resource_max_offset)?;
        let resource_max_map = if resource_max_cache == 0 {
            0
        } else {
            let cache_type =
                read_u64_le(&read_process_bytes(process, resource_max_cache, 8)?, 0)? as usize;
            if cache_type != code.types_address + INT_MAP_TYPE_INDEX * 32 {
                return Err("lastResourceAttributesMax is not a HashLink IntMap".to_owned());
            }
            read_object_pointer_field(process, resource_max_cache, root.int_map_handle_offset)?
        };
        let cached_max_health =
            read_int_map_f64(process, code.types_address, resource_max_map, 27)?
                .filter(|value| value.is_finite() && *value > 0.0)
                .unwrap_or(raw_max_health);
        let mut hud_max_health = hud_health_gauge.and_then(|gauge| {
            let gauge_type = read_process_bytes(process, gauge, 8).ok()?;
            if read_u64_le(&gauge_type, 0).ok()? as usize
                != code.types_address + ATTRIBUTE_BAR_TYPE_INDEX * 32
                || read_object_pointer_field(process, gauge, root.attribute_bar_unit_offset).ok()?
                    != hero
            {
                return None;
            }
            let value = read_process_bytes(process, gauge + root.base_gauge_max_offset, 8).ok()?;
            let value = read_f64_le(&value, 0).ok()?;
            (value.is_finite() && value > 0.0).then_some(value)
        });
        if hud_max_health.is_none() && allow_hud_discovery {
            *hud_health_gauge = None;
            if let Some((gauge, shield_gauge, value)) =
                read_hud_max_health(process, code, root, game_app, hero)?
            {
                *hud_health_gauge = Some(gauge);
                *hud_shield_gauge = shield_gauge;
                hud_max_health = Some(value);
            }
        }
        let max_health = hud_max_health.unwrap_or(cached_max_health);
        let health_regen = read_f64_le(
            &read_process_bytes(process, attributes + root.health_regen_offset, 8)?,
            0,
        )?;
        let raw_shield = read_f64_le(
            &read_process_bytes(process, attributes + root.shield_offset, 8)?,
            0,
        )?;
        let hud_shield_ratio = hud_shield_gauge.and_then(|gauge| {
            let gauge_type = read_process_bytes(process, gauge, 8).ok()?;
            if read_u64_le(&gauge_type, 0).ok()? as usize != code.types_address + 4_672 * 32 {
                return None;
            }
            let value =
                read_process_bytes(process, gauge + root.base_gauge_value_offset, 8).ok()?;
            let value = read_f64_le(&value, 0).ok()?;
            (value.is_finite() && value >= 0.0).then_some(value)
        });
        let shield_gauge_available = hud_shield_ratio.is_some();
        let shield_capacity = hud_shield_ratio
            .map(|ratio| (ratio * max_health).ceil())
            .unwrap_or(0.0);
        let shield_gauge_visible = hud_shield_gauge
            .and_then(|gauge| {
                read_process_bytes(process, gauge + root.h2d_visible_offset, 1)
                    .ok()
                    .map(|value| value[0] != 0)
            })
            .unwrap_or(false);
        let shield = if shield_gauge_visible {
            shield_capacity
        } else {
            raw_shield
        };
        let shield_ratio = if max_health > 0.0 {
            shield / max_health
        } else {
            0.0
        };
        let special_energy = read_f64_le(
            &read_process_bytes(process, attributes + root.special_energy_offset, 8)?,
            0,
        )?;
        let special_energy_regen = read_f64_le(
            &read_process_bytes(process, attributes + root.special_energy_regen_offset, 8)?,
            0,
        )?;
        if [x, y, z, rotation]
            .iter()
            .any(|value| !value.is_finite() || value.abs() > 10_000_000.0)
        {
            return Err("Hero transform failed sanity validation".to_owned());
        }
        if !(0..=1_000).contains(&level)
            || [
                vitality,
                health,
                max_health,
                health_regen,
                shield,
                special_energy,
                special_energy_regen,
            ]
            .iter()
            .any(|value| !value.is_finite() || value.abs() > 1_000_000_000.0)
            || health < 0.0
            || max_health < 0.0
            || shield < 0.0
        {
            return Err("Hero status failed sanity validation".to_owned());
        }
        let mut party = Vec::new();
        let group_players = read_group_players(process, code, root, player)?;
        let mut active_party_heroes = Vec::new();
        for member_player in group_players {
            if member_player == player || party.len() >= 3 {
                continue;
            }
            if let Some(member) = sample_party_member(
                process,
                code,
                member_player,
                x,
                y,
                z,
                allow_hud_discovery,
                party_gauge_cache,
            )? {
                let member_hero =
                    read_object_pointer_field(process, member_player, root.player_hero_offset)?;
                active_party_heroes.push(member_hero);
                party.push(member);
            }
        }
        party_gauge_cache.retain(|entry| active_party_heroes.contains(&entry.hero));
        if allow_hud_discovery {
            // Soft-fail: a large progress map must not drop the whole sample.
            if let Ok(completed) = read_completed_elements(process, code, root, player) {
                *completed_elements_cache = completed;
            }
        }
        let currencies = read_currencies(process, code, root, player, hero);
        let currency_counters = read_currency_counters(process, code, root, player);
        let instance = read_instance_context(process, code, hero);
        let time_of_day = read_time_of_day(process, code, hero);
        let camera_yaw = read_camera_yaw(process, code, game_app, x, y);
        Ok(TelemetrySample {
            game_app,
            player,
            hero,
            name,
            uid,
            class_name,
            level,
            in_combat,
            health,
            vitality,
            max_health,
            health_regen,
            shield,
            shield_ratio,
            shield_capacity,
            shield_gauge_visible,
            raw_shield,
            shield_gauge_available,
            special_energy,
            special_energy_regen,
            currencies,
            currency_counters,
            x,
            y,
            z,
            rotation,
            camera_yaw,
            party,
            party_heroes: active_party_heroes,
            instance,
            time_of_day,
            completed_elements: completed_elements_cache.clone(),
        })
    }

    pub fn watch(path: &Path, interval_ms: u64) -> Result<(), String> {
        if !(50..=5_000).contains(&interval_ms) {
            return Err("watch interval must be between 50 and 5000 ms".to_owned());
        }
        let mut attached: Option<(OwnedHandle, CodeAnchor)> = None;
        let mut sequence = 0_u64;
        let mut hud_health_gauge = None;
        let mut hud_shield_gauge = None;
        let mut party_gauge_cache = Vec::new();
        let mut completed_elements_cache = Vec::new();
        let mut observed_dps = ObservedDps::new();
        let mut last_good_player_name = String::new();
        let mut last_good_player_uid = String::new();
        let mut consecutive_sample_failures = 0_u32;
        // ~15s of soft failures at 100ms before forcing a reattach (dead handle /
        // wineserver blip). Obelisk teleports usually recover in <2s without this.
        const SOFT_REATTACH_AFTER: u32 = 150;
        loop {
            sequence = sequence.wrapping_add(1);
            let timestamp_ms = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis();

            if attached.is_none() {
                match attach_for_watch() {
                    Ok(pair) => {
                        attached = Some(pair);
                        hud_health_gauge = None;
                        hud_shield_gauge = None;
                        party_gauge_cache.clear();
                        completed_elements_cache.clear();
                        observed_dps = ObservedDps::new();
                        // Keep last_good_player_name across soft reattaches so
                        // teleport blips do not wipe the display name.
                        consecutive_sample_failures = 0;
                    }
                    Err(error) => {
                        std::fs::write(path, waiting_report(sequence, timestamp_ms, &error))
                            .map_err(|write_error| {
                                format!("could not write {}: {write_error}", path.display())
                            })?;
                        std::thread::sleep(Duration::from_millis(interval_ms));
                        continue;
                    }
                }
            }

            let (report, drop_attach) = {
                let (process, code) = attached
                    .as_ref()
                    .expect("attach succeeded or loop continued");
                match sample_telemetry(
                    process,
                    code,
                    &mut hud_health_gauge,
                    &mut hud_shield_gauge,
                    sequence == 1 || sequence % 10 == 0,
                    &mut party_gauge_cache,
                    &mut completed_elements_cache,
                ) {
                    Ok(mut sample) => {
                        consecutive_sample_failures = 0;
                        // Drop sticky name when the live uid changes (character swap).
                        if !sample.uid.is_empty()
                            && !last_good_player_uid.is_empty()
                            && sample.uid != last_good_player_uid
                        {
                            last_good_player_name.clear();
                        }
                        if !sample.uid.is_empty() {
                            last_good_player_uid = sample.uid.clone();
                        }
                        if !sample.name.is_empty() && !looks_like_element_kind_id(&sample.name) {
                            last_good_player_name = sample.name.clone();
                        } else if !last_good_player_name.is_empty()
                            && (sample.name.is_empty()
                                || looks_like_element_kind_id(&sample.name))
                        {
                            sample.name = last_good_player_name.clone();
                        }
                        // Final guard: never write a prefab id into player.name.
                        if looks_like_element_kind_id(&sample.name) {
                            sample.name.clear();
                            if !last_good_player_name.is_empty() {
                                sample.name = last_good_player_name.clone();
                            }
                        }
                        let now = Instant::now();
                        let foes = read_live_foe_health(process, code, sample.hero)
                            .unwrap_or_default();
                        observed_dps.update(&foes, sample.in_combat, now);
                        let dps_elapsed = observed_dps.elapsed(now);
                        let dps_rate = if dps_elapsed > 0.0 {
                            observed_dps.total / dps_elapsed
                        } else {
                            0.0
                        };
                        let enemies = read_nearby_enemies(
                            process,
                            code,
                            sample.hero,
                            sample.x,
                            sample.y,
                            sample.z,
                        )
                        .unwrap_or_default();
                        let layer_players = read_layer_players(
                            process,
                            code,
                            sample.hero,
                            sample.player,
                            &sample.party_heroes,
                            sample.x,
                            sample.y,
                            sample.z,
                        )
                        .unwrap_or_default();
                        let interactibles = read_nearby_interactibles(
                            process,
                            code,
                            sample.hero,
                            sample.x,
                            sample.y,
                            sample.z,
                        )
                        .unwrap_or_default();
                        let party_json = sample
                            .party
                            .iter()
                            .map(|member| {
                                format!(
                                    "{{\"name\":{},\"uid\":{},\"class\":{},\"level\":{},\"connected\":{},\"health\":{},\"max_health\":{},\"shield\":{},\"position\":{{\"x\":{},\"y\":{},\"z\":{}}},\"heading\":{},\"distance\":{}}}",
                                    json_string(&member.name),
                                    json_string(&member.uid),
                                    json_string(&member.class_name),
                                    member.level,
                                    member.connected,
                                    member.health,
                                    member.max_health,
                                    member.shield,
                                    member.x,
                                    member.y,
                                    member.z,
                                    member.rotation,
                                    member.distance,
                                )
                            })
                            .collect::<Vec<_>>()
                            .join(",");
                        let enemies_json = enemies
                            .iter()
                            .map(|enemy| {
                                format!(
                                    "{{\"id\":\"0x{:x}\",\"kind\":{},\"position\":{{\"x\":{},\"y\":{},\"z\":{}}}}}",
                                    enemy.address,
                                    json_string(&enemy.kind),
                                    enemy.x,
                                    enemy.y,
                                    enemy.z,
                                )
                            })
                            .collect::<Vec<_>>()
                            .join(",");
                        let players_json = layer_players
                            .iter()
                            .map(|other| {
                                format!(
                                    "{{\"id\":\"0x{:x}\",\"name\":{},\"uid\":{},\"class\":{},\"level\":{},\"position\":{{\"x\":{},\"y\":{},\"z\":{}}},\"heading\":{},\"distance\":{}}}",
                                    other.address,
                                    json_string(&other.name),
                                    json_string(&other.uid),
                                    json_string(&other.class_name),
                                    other.level,
                                    other.x,
                                    other.y,
                                    other.z,
                                    other.rotation,
                                    other.distance,
                                )
                            })
                            .collect::<Vec<_>>()
                            .join(",");
                        let interactibles_json = interactibles
                            .iter()
                            .map(|item| {
                                format!(
                                    "{{\"id\":\"0x{:x}\",\"kind\":{},\"name\":{},\"position\":{{\"x\":{},\"y\":{},\"z\":{}}}}}",
                                    item.address,
                                    json_string(item.category),
                                    json_string(&item.name),
                                    item.x,
                                    item.y,
                                    item.z,
                                )
                            })
                            .collect::<Vec<_>>()
                            .join(",");
                        let completed_elements_json = sample
                            .completed_elements
                            .iter()
                            .map(|value| json_string(value))
                            .collect::<Vec<_>>()
                            .join(",");
                        let instance_json = format!(
                            "{{\"type\":{},\"map_id\":{},\"is_rift\":{},\"is_dungeon\":{},\"is_world_map\":{},\"activity_kind\":{}}}",
                            json_string(sample.instance.kind),
                            json_string(&sample.instance.map_id),
                            sample.instance.is_rift,
                            sample.instance.is_dungeon,
                            sample.instance.is_world_map,
                            json_string(&sample.instance.activity_kind),
                        );
                        let time_of_day_json = match &sample.time_of_day {
                            Some(tod) => format!(
                                "{{\"factor\":{},\"elapsed\":{},\"speed\":{},\"paused\":{}}}",
                                tod.factor, tod.elapsed, tod.speed, tod.paused,
                            ),
                            None => "null".to_owned(),
                        };
                        let camera_yaw_json = if sample.camera_yaw.is_finite() {
                            format!("{}", sample.camera_yaw)
                        } else {
                            "null".to_owned()
                        };
                        let currencies_json = sample
                            .currencies
                            .iter()
                            .map(|currency| {
                                format!(
                                    "{{\"kind\":{},\"amount\":{}}}",
                                    json_string(&currency.kind),
                                    currency.amount,
                                )
                            })
                            .collect::<Vec<_>>()
                            .join(",");
                        let currency_counters_json = sample
                            .currency_counters
                            .iter()
                            .map(|(key, value)| {
                                format!("{}:{}", json_string(key), value)
                            })
                            .collect::<Vec<_>>()
                            .join(",");
                        (
                            format!(
                                "{{\"schema\":1,\"bridge_version\":\"0.23.6\",\"state\":\"connected\",\"sequence\":{sequence},\"timestamp_ms\":{timestamp_ms},\"game_app_address\":\"0x{:x}\",\"player_address\":\"0x{:x}\",\"hero_address\":\"0x{:x}\",\"player\":{{\"name\":{},\"uid\":{},\"class\":{},\"level\":{},\"in_combat\":{},\"vitality\":{},\"health\":{},\"max_health\":{},\"health_regen\":{},\"shield\":{},\"shield_ratio\":{},\"shield_capacity\":{},\"shield_gauge_visible\":{},\"raw_shield\":{},\"shield_gauge_available\":{},\"special_energy\":{},\"special_energy_regen\":{},\"currencies\":[{currencies_json}],\"currency_counters\":{{{currency_counters_json}}}}},\"position\":{{\"x\":{},\"y\":{},\"z\":{}}},\"rotation_z\":{},\"camera_yaw\":{camera_yaw_json},\"party\":[{}],\"enemies\":[{}],\"players\":[{}],\"interactibles\":[{}],\"instance\":{instance_json},\"time_of_day\":{time_of_day_json},\"completed_elements\":[{}],\"dps\":{{\"mode\":\"observed_nearby\",\"fight_id\":{},\"current\":{},\"total\":{},\"elapsed\":{},\"in_combat\":{},\"damage_skills\":[{{\"skill\":\"Observed nearby damage\",\"total\":{},\"hits\":0,\"crits\":0,\"max\":0}}],\"healing_skills\":[]}}}}\n",
                                sample.game_app,
                                sample.player,
                                sample.hero,
                                json_string(&sample.name),
                                json_string(&sample.uid),
                                json_string(&sample.class_name),
                                sample.level,
                                sample.in_combat,
                                sample.vitality,
                                sample.health,
                                sample.max_health,
                                sample.health_regen,
                                sample.shield,
                                sample.shield_ratio,
                                sample.shield_capacity,
                                sample.shield_gauge_visible,
                                sample.raw_shield,
                                sample.shield_gauge_available,
                                sample.special_energy,
                                sample.special_energy_regen,
                                sample.x,
                                sample.y,
                                sample.z,
                                sample.rotation,
                                party_json,
                                enemies_json,
                                players_json,
                                interactibles_json,
                                completed_elements_json,
                                observed_dps.fight_id,
                                dps_rate,
                                observed_dps.total,
                                dps_elapsed,
                                observed_dps.active,
                                observed_dps.total
                            ),
                            false,
                        )
                    }
                    Err(error) => {
                        consecutive_sample_failures =
                            consecutive_sample_failures.saturating_add(1);
                        // Drop stale HUD pointers so they rediscover after teleport.
                        hud_health_gauge = None;
                        hud_shield_gauge = None;
                        party_gauge_cache.clear();
                        let soft = is_transient_sample_error(&error);
                        let drop = should_reattach(&error)
                            || (soft && consecutive_sample_failures >= SOFT_REATTACH_AFTER)
                            || (!soft && consecutive_sample_failures >= 5);
                        (
                            waiting_report(sequence, timestamp_ms, &error),
                            drop,
                        )
                    }
                }
            };
            if drop_attach {
                attached = None;
            }
            std::fs::write(path, report)
                .map_err(|error| format!("could not write {}: {error}", path.display()))?;
            std::thread::sleep(Duration::from_millis(interval_ms));
        }
    }

    pub fn run() -> Result<String, String> {
        let process_id = find_farever_process()?;
        let process =
            OwnedHandle::new(unsafe { OpenProcess(FAREVER_READ_ACCESS, FALSE, process_id) })
                .ok_or_else(|| {
                    format!(
                        "opening Farever.exe read-only failed (Win32 error {})",
                        last_error()
                    )
                })?;

        let modules = loaded_modules(process_id)?;
        let module = modules
            .iter()
            .find(|module| module.name.eq_ignore_ascii_case("Farever.exe"))
            .ok_or_else(|| "Farever.exe main module was not found".to_owned())?;
        let libhl_module = modules
            .iter()
            .find(|module| module.name.eq_ignore_ascii_case("libhl.dll"))
            .ok_or_else(|| "libhl.dll was not found in the Farever process".to_owned())?;
        let executable_path = module.path.clone();
        let fingerprint = fingerprint_executable(&executable_path)?;
        if module.size != fingerprint.image_size {
            return Err(format!(
                "loaded Farever module size {} does not match PE image size {}",
                module.size, fingerprint.image_size
            ));
        }
        if !matches_supported_profile(&fingerprint) {
            return Err(format!(
                concat!(
                    "unsupported Farever build: machine=0x{:04x}, ",
                    "timestamp={}, image_size={}, file_size={}, crc32={:08x}"
                ),
                fingerprint.machine,
                fingerprint.pe_timestamp,
                fingerprint.image_size,
                fingerprint.file_size,
                fingerprint.crc32
            ));
        }
        verify_live_pe_header(&process, module)?;
        verify_live_pe_header(&process, libhl_module)?;
        let application_directory = parent_path(&executable_path);
        let hlboot_path = format!("{application_directory}\\hlboot.dat");
        let hlboot_fingerprint = fingerprint_bytecode(&hlboot_path)?;
        if hlboot_fingerprint.version != SUPPORTED_HLBOOT_VERSION
            || hlboot_fingerprint.file_size != SUPPORTED_HLBOOT_FILE_SIZE
            || hlboot_fingerprint.crc32 != SUPPORTED_HLBOOT_CRC32
        {
            return Err(format!(
                concat!(
                    "unsupported Farever hlboot.dat: version={}, ",
                    "file_size={}, crc32={:08x}"
                ),
                hlboot_fingerprint.version, hlboot_fingerprint.file_size, hlboot_fingerprint.crc32
            ));
        }
        let runtime_anchor = read_runtime_anchor(&process, module)?;
        let code_anchor = read_code_anchor(&process, &runtime_anchor, true)?;
        let module_reports = modules
            .iter()
            .map(|module| module_json(module, application_directory))
            .collect::<Result<Vec<_>, _>>()?;

        Ok(format!(
            concat!(
                "{{",
                "\"schema\":1,",
                "\"bridge_version\":\"0.9.0\",",
                "\"access\":\"query+read-only\",",
                "\"build_supported\":true,",
                "\"build_profile\":{},",
                "\"process_id\":{},",
                "\"module\":{{",
                "\"name\":{},",
                "\"path\":{},",
                "\"base_address\":\"0x{:x}\",",
                "\"size\":{},",
                "\"fingerprint\":{{",
                "\"machine\":\"0x{:04x}\",",
                "\"pe_timestamp\":{},",
                "\"image_size\":{},",
                "\"file_size\":{},",
                "\"crc32\":\"{:08x}\"",
                "}}",
                "}}",
                ",\"loaded_module_count\":{},",
                "\"loaded_modules\":[{}],",
                "\"hlboot\":{{",
                "\"path\":{},",
                "\"bytecode_version\":{},",
                "\"file_size\":{},",
                "\"crc32\":\"{:08x}\"",
                "}}",
                ",\"live_memory_verification\":{{",
                "\"maximum_single_read\":4096,",
                "\"farever_pe_header\":true,",
                "\"libhl_pe_header\":true",
                "}}",
                ",\"hashlink_runtime_anchor\":{{",
                "\"main_context_pointer_rva\":\"0x{:x}\",",
                "\"main_context_pointer_address\":\"0x{:x}\",",
                "\"main_context_address\":\"0x{:x}\",",
                "\"file_address\":\"0x{:x}\",",
                "\"code_address\":\"0x{:x}\",",
                "\"module_address\":\"0x{:x}\",",
                "\"file_name\":\"hlboot.dat\",",
                "\"module_code_cross_check\":true",
                "}}",
                ",\"hashlink_code_metadata\":{{",
                "\"version\":{},",
                "\"type_count\":{},",
                "\"global_count\":{},",
                "\"function_count\":{},",
                "\"entrypoint\":{},",
                "\"types_address\":\"0x{:x}\",",
                "\"globals_address\":\"0x{:x}\",",
                "\"validated_globals\":[",
                "{{\"name\":\"st.Player\",\"type_index\":{},\"global_index\":{},\"type_address\":\"0x{:x}\",\"object_metadata_address\":\"0x{:x}\",\"slot_address\":\"0x{:x}\",\"value_address\":\"0x{:x}\",\"value_type_index\":{},\"value_type_name\":\"st.$Player\",\"value_type_address\":\"0x{:x}\",\"value_type_matches\":true}},",
                "{{\"name\":\"ent.Hero\",\"type_index\":{},\"global_index\":{},\"type_address\":\"0x{:x}\",\"object_metadata_address\":\"0x{:x}\",\"slot_address\":\"0x{:x}\",\"value_address\":\"0x{:x}\",\"value_type_index\":{},\"value_type_name\":\"ent.$Hero\",\"value_type_address\":\"0x{:x}\",\"value_type_matches\":true}},",
                "{{\"name\":\"st.Group\",\"type_index\":{},\"global_index\":{},\"type_address\":\"0x{:x}\",\"object_metadata_address\":\"0x{:x}\",\"slot_address\":\"0x{:x}\",\"value_address\":\"0x{:x}\",\"value_type_index\":{},\"value_type_name\":\"st.$Group\",\"value_type_address\":\"0x{:x}\",\"value_type_matches\":true}}",
                "]",
                "}}",
                ",\"live_player_root\":{{",
                "\"source\":\"global[955] -> $App.inst -> GameApp\",",
                "\"app_static_holder_address\":\"0x{:x}\",",
                "\"game_app_address\":\"0x{:x}\",",
                "\"player_address\":\"0x{:x}\",",
                "\"hero_address\":\"0x{:x}\",",
                "\"type_checks_passed\":true",
                "}}",
                ",\"telemetry\":{{",
                "\"position\":{{\"x\":{},\"y\":{},\"z\":{}}},",
                "\"rotation_z\":{}",
                "}}",
                "}}"
            ),
            json_string(SUPPORTED_PROFILE_NAME),
            process_id,
            json_string(&module.name),
            json_string(&executable_path),
            module.base_address,
            module.size,
            fingerprint.machine,
            fingerprint.pe_timestamp,
            fingerprint.image_size,
            fingerprint.file_size,
            fingerprint.crc32,
            module_reports.len(),
            module_reports.join(","),
            json_string(&hlboot_path),
            hlboot_fingerprint.version,
            hlboot_fingerprint.file_size,
            hlboot_fingerprint.crc32,
            SUPPORTED_MAIN_CONTEXT_POINTER_RVA,
            runtime_anchor.pointer_address,
            runtime_anchor.context_address,
            runtime_anchor.file_address,
            runtime_anchor.code_address,
            runtime_anchor.module_address,
            SUPPORTED_HLBOOT_VERSION,
            SUPPORTED_TYPE_COUNT,
            SUPPORTED_GLOBAL_COUNT,
            SUPPORTED_FUNCTION_COUNT,
            SUPPORTED_ENTRYPOINT,
            code_anchor.types_address,
            code_anchor.globals_address,
            PLAYER_TYPE_INDEX,
            PLAYER_GLOBAL_INDEX,
            code_anchor.player.type_address,
            code_anchor.player.object_metadata_address,
            code_anchor.player.slot_address,
            code_anchor.player.value_address,
            PLAYER_STATIC_TYPE_INDEX,
            code_anchor.player.value_type_address,
            HERO_TYPE_INDEX,
            HERO_GLOBAL_INDEX,
            code_anchor.hero.type_address,
            code_anchor.hero.object_metadata_address,
            code_anchor.hero.slot_address,
            code_anchor.hero.value_address,
            HERO_STATIC_TYPE_INDEX,
            code_anchor.hero.value_type_address,
            GROUP_TYPE_INDEX,
            GROUP_GLOBAL_INDEX,
            code_anchor.group.type_address,
            code_anchor.group.object_metadata_address,
            code_anchor.group.slot_address,
            code_anchor.group.value_address,
            GROUP_STATIC_TYPE_INDEX,
            code_anchor.group.value_type_address,
            code_anchor.player_root.app_static_holder_address,
            code_anchor.player_root.game_app_address,
            code_anchor.player_root.player_address,
            code_anchor.player_root.hero_address,
            code_anchor.player_root.position_x,
            code_anchor.player_root.position_y,
            code_anchor.player_root.position_z,
            code_anchor.player_root.rotation_z
        ))
    }
}

#[cfg(windows)]
fn main() {
    let mut output_path = None;
    let mut watch_interval_ms = None;
    let mut arguments = std::env::args_os().skip(1);
    while let Some(argument) = arguments.next() {
        if argument == "--output" {
            let Some(path) = arguments.next() else {
                eprintln!("farever-atlas-bridge: --output requires a path");
                std::process::exit(2);
            };
            output_path = Some(path);
        } else if argument == "--watch-ms" {
            let Some(value) = arguments.next() else {
                eprintln!("farever-atlas-bridge: --watch-ms requires a value");
                std::process::exit(2);
            };
            watch_interval_ms = value.to_string_lossy().parse::<u64>().ok();
            if watch_interval_ms.is_none() {
                eprintln!("farever-atlas-bridge: --watch-ms must be an integer");
                std::process::exit(2);
            }
        } else {
            eprintln!(
                "farever-atlas-bridge: unknown argument {}",
                argument.to_string_lossy()
            );
            std::process::exit(2);
        }
    }

    if let Some(interval_ms) = watch_interval_ms {
        let Some(path) = output_path else {
            eprintln!("farever-atlas-bridge: watch mode requires --output");
            std::process::exit(2);
        };
        if let Err(error) = windows_bridge::watch(std::path::Path::new(&path), interval_ms) {
            eprintln!("farever-atlas-bridge: {error}");
            let _ = std::fs::write(&path, format!("farever-atlas-bridge: {error}\n"));
            std::process::exit(1);
        }
        return;
    }

    match windows_bridge::run() {
        Ok(report) => {
            println!("{report}");
            if let Some(path) = output_path {
                if let Err(error) = std::fs::write(&path, format!("{report}\n")) {
                    eprintln!(
                        "farever-atlas-bridge: could not write {}: {error}",
                        path.to_string_lossy()
                    );
                    std::process::exit(1);
                }
            }
        }
        Err(error) => {
            eprintln!("farever-atlas-bridge: {error}");
            if let Some(path) = output_path {
                let _ = std::fs::write(path, format!("farever-atlas-bridge: {error}\n"));
            }
            std::process::exit(1);
        }
    }
}
