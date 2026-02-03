import SwiftUI

enum Assets {
    static let bgBase = "bg_base_01"
    static let pawprint = "pawprint_common_01"

    static func petBase(for state: SharedState) -> String {
        // Phase1: キャラIDで分岐する前提。まずは固定。
        switch state.lens {
        case .cute:
            return "pet_cat_orange_base"
        case .chic:
            return "pet_cat_orange_scarf"
        }
    }

    static func petBlink(for state: SharedState) -> String {
        "pet_cat_orange_blink"
    }

    static func atmosphereFrame(for weather: Weather, seed: Int) -> String? {
        // seed: 0..2 想定（thunderは0..1）
        switch weather {
        case .clear:
            return "atm_sun_0\(1 + (seed % 2))"
        case .rain:
            return "atm_rain_0\(1 + (seed % 3))"
        case .snow:
            return "atm_snow_0\(1 + (seed % 3))"
        case .wind:
            return "atm_wind_0\(1 + (seed % 3))"
        case .thunder:
            return "atm_thunder_0\(1 + (seed % 2))"
        }
    }

    static func nameOpacity(for lens: Lens) -> Double {
        switch lens {
        case .cute: return 0.55
        case .chic: return 0.35
        }
    }
}

