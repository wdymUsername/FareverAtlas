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
    use std::collections::HashMap;
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
    const HERO_POS_X_FIELD_INDEX: usize = 27;
    const HERO_POS_Y_FIELD_INDEX: usize = 28;
    const HERO_POS_Z_FIELD_INDEX: usize = 29;
    const HERO_ROTATION_Z_FIELD_INDEX: usize = 30;
    const HERO_LAYER_FIELD_INDEX: usize = 14;
    const GAME_LAYER_TYPE_INDEX: usize = 782;
    const GAME_LAYER_UNITS_FIELD_INDEX: usize = 44;
    const FOE_TYPE_INDEX: usize = 1_381;
    const STATE_TYPE_INDEX: usize = 781;
    const STATE_REMOVED_FIELD_INDEX: usize = 0;
    const FOE_SUMMON_OWNER_FIELD_INDEX: usize = 164;
    // Runtime field indexes include inherited fields. These indexes are
    // derived from the supported hlboot.dat metadata, never guessed offsets.
    const PLAYER_NAME_FIELD_INDEX: usize = 29;
    const PLAYER_UID_FIELD_INDEX: usize = 28;
    const PLAYER_GROUP_FIELD_INDEX: usize = 37;
    const PLAYER_PROGRESS_FIELD_INDEX: usize = 36;
    const PLAYER_HERO_DATA_FIELD_INDEX: usize = 35;
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
    const PROGRESS_ELEMENTS_FIELD_INDEX: usize = 21;
    const MAP_DATA_TYPE_INDEX: usize = 1_038;
    const MAP_DATA_MAP_FIELD_INDEX: usize = 4;
    const STRING_MAP_TYPE_INDEX: usize = 66;
    const STRING_MAP_HANDLE_FIELD_INDEX: usize = 0;
    const COMPLETION_PROXY_TYPE_INDEX: usize = 23_065;
    const COMPLETION_PROXY_COMPLETED_FIELD_INDEX: usize = 2;
    const HERO_DATA_TYPE_INDEX: usize = 1_365;
    const HERO_DATA_PROGRESS_FIELD_INDEX: usize = 44;
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
        if succeeded == FALSE || bytes_read != size {
            return Err(format!(
                "read-only process read at 0x{address:x} failed: requested {size}, read {bytes_read} (Win32 error {})",
                last_error()
            ));
        }
        Ok(buffer)
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
        position_x_offset: usize,
        position_y_offset: usize,
        position_z_offset: usize,
        rotation_z_offset: usize,
        layer_offset: usize,
        game_layer_units_offset: usize,
        state_removed_offset: usize,
        foe_summon_owner_offset: usize,
        player_name_offset: usize,
        player_uid_offset: usize,
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
        progress_elements_offset: usize,
        map_data_map_offset: usize,
        string_map_handle_offset: usize,
        completion_proxy_completed_offset: usize,
        hero_data_progress_offset: usize,
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

            if damage > 0.0 {
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
        let game_layer_units_offset = object_field_offset(
            process,
            types_address + GAME_LAYER_TYPE_INDEX * 32,
            GAME_LAYER_UNITS_FIELD_INDEX,
        )?;
        let state_removed_offset = object_field_offset(
            process,
            types_address + STATE_TYPE_INDEX * 32,
            STATE_REMOVED_FIELD_INDEX,
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
        let hero_data_progress_offset = object_field_offset(
            process,
            types_address + HERO_DATA_TYPE_INDEX * 32,
            HERO_DATA_PROGRESS_FIELD_INDEX,
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
            position_x_offset,
            position_y_offset,
            position_z_offset,
            rotation_z_offset,
            layer_offset,
            game_layer_units_offset,
            state_removed_offset,
            foe_summon_owner_offset,
            player_name_offset,
            player_uid_offset,
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
            progress_elements_offset,
            map_data_map_offset,
            string_map_handle_offset,
            completion_proxy_completed_offset,
            hero_data_progress_offset,
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
        // unbounded scan.
        let bytes = read_process_bytes(process, pointer, 128)?;
        let mut units = Vec::with_capacity(64);
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
        let bytes = read_process_bytes(process, value_address, 64)?;
        let mut units = Vec::with_capacity(32);
        for pair in bytes.chunks_exact(2) {
            let unit = u16::from_le_bytes([pair[0], pair[1]]);
            if unit == 0 {
                let value = String::from_utf16(&units)
                    .map_err(|_| format!("{label} is not valid UTF-16"))?;
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
            units.push(unit);
        }
        Err(format!("{label} exceeds the bounded identifier read"))
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
        x: f64,
        y: f64,
        z: f64,
        rotation: f64,
        party: Vec<PartySample>,
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
        let entries = read_process_bytes(process, values, maxentries.saturating_mul(16))?;
        let expected_value_type = code.types_address + COMPLETION_PROXY_TYPE_INDEX * 32;
        let mut completed = Vec::new();
        for index in 0..maxentries {
            let offset = index * 16;
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
            "{{\"schema\":1,\"bridge_version\":\"0.11.0\",\"state\":\"waiting\",\"sequence\":{sequence},\"timestamp_ms\":{timestamp_ms},\"message\":{}}}\n",
            json_string(message)
        )
    }

    fn should_reattach(error: &str) -> bool {
        error.contains("Win32 error")
            || error.contains("process read")
            || error.contains("Farever.exe is not running")
            || error.contains("main module was not found")
            || error.contains("libhl.dll was not found")
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
        let name = read_hashlink_string(process, code.types_address, name_pointer, "party name")?;
        let uid = read_hashlink_string(process, code.types_address, uid_pointer, "party uid")?;
        let unit_kind = read_object_pointer_field(process, hero, root.unit_kind_offset)?;
        let class_name =
            read_hashlink_identifier(process, code.types_address, unit_kind, "party unit kind")
                .unwrap_or_default();
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
        let name = read_hashlink_string(process, code.types_address, name_pointer, "player name")?;
        let uid_pointer = read_object_pointer_field(process, player, root.player_uid_offset)?;
        let uid = read_hashlink_string(process, code.types_address, uid_pointer, "player uid")?;
        let unit_kind = read_object_pointer_field(process, hero, root.unit_kind_offset)?;
        let class_name =
            read_hashlink_identifier(process, code.types_address, unit_kind, "hero unit kind")
                .unwrap_or_default();
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
            *completed_elements_cache = read_completed_elements(process, code, root, player)?;
        }
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
            x,
            y,
            z,
            rotation,
            party,
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
                    Ok(sample) => {
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
                        let completed_elements_json = sample
                            .completed_elements
                            .iter()
                            .map(|value| json_string(value))
                            .collect::<Vec<_>>()
                            .join(",");
                        (
                            format!(
                                "{{\"schema\":1,\"bridge_version\":\"0.11.0\",\"state\":\"connected\",\"sequence\":{sequence},\"timestamp_ms\":{timestamp_ms},\"game_app_address\":\"0x{:x}\",\"player_address\":\"0x{:x}\",\"hero_address\":\"0x{:x}\",\"player\":{{\"name\":{},\"uid\":{},\"class\":{},\"level\":{},\"in_combat\":{},\"vitality\":{},\"health\":{},\"max_health\":{},\"health_regen\":{},\"shield\":{},\"shield_ratio\":{},\"shield_capacity\":{},\"shield_gauge_visible\":{},\"raw_shield\":{},\"shield_gauge_available\":{},\"special_energy\":{},\"special_energy_regen\":{}}},\"position\":{{\"x\":{},\"y\":{},\"z\":{}}},\"rotation_z\":{},\"party\":[{}],\"completed_elements\":[{}],\"dps\":{{\"mode\":\"observed_nearby\",\"fight_id\":{},\"current\":{},\"total\":{},\"elapsed\":{},\"in_combat\":{},\"damage_skills\":[{{\"skill\":\"Observed nearby damage\",\"total\":{},\"hits\":0,\"crits\":0,\"max\":0}}],\"healing_skills\":[]}}}}\n",
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
                    Err(error) => (
                        waiting_report(sequence, timestamp_ms, &error),
                        should_reattach(&error),
                    ),
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
