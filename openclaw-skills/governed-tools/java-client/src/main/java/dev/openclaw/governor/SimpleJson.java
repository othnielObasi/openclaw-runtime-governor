package dev.openclaw.governor;

import java.util.*;

/**
 * Minimal JSON parser — zero dependencies.
 * Handles objects, arrays, strings, numbers, booleans, and null.
 * Good enough for Governor API responses.
 */
class SimpleJson {

    static Object parse(String json) {
        return new Parser(json.trim()).parseValue();
    }

    private static class Parser {
        private final String src;
        private int pos;

        Parser(String src) {
            this.src = src;
        }

        Object parseValue() {
            skipWhitespace();
            if (pos >= src.length()) return null;
            char c = src.charAt(pos);
            if (c == '{') return parseObject();
            if (c == '[') return parseArray();
            if (c == '"') return parseString();
            if (c == 't' || c == 'f') return parseBoolean();
            if (c == 'n') return parseNull();
            return parseNumber();
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> parseObject() {
            Map<String, Object> map = new LinkedHashMap<>();
            pos++; // skip {
            skipWhitespace();
            if (pos < src.length() && src.charAt(pos) == '}') { pos++; return map; }
            while (pos < src.length()) {
                skipWhitespace();
                String key = parseString();
                skipWhitespace();
                expect(':');
                Object value = parseValue();
                map.put(key, value);
                skipWhitespace();
                if (pos < src.length() && src.charAt(pos) == ',') { pos++; continue; }
                break;
            }
            skipWhitespace();
            if (pos < src.length() && src.charAt(pos) == '}') pos++;
            return map;
        }

        List<Object> parseArray() {
            List<Object> list = new ArrayList<>();
            pos++; // skip [
            skipWhitespace();
            if (pos < src.length() && src.charAt(pos) == ']') { pos++; return list; }
            while (pos < src.length()) {
                list.add(parseValue());
                skipWhitespace();
                if (pos < src.length() && src.charAt(pos) == ',') { pos++; continue; }
                break;
            }
            skipWhitespace();
            if (pos < src.length() && src.charAt(pos) == ']') pos++;
            return list;
        }

        String parseString() {
            pos++; // skip opening "
            StringBuilder sb = new StringBuilder();
            while (pos < src.length()) {
                char c = src.charAt(pos);
                if (c == '\\') {
                    pos++;
                    if (pos < src.length()) {
                        char esc = src.charAt(pos);
                        switch (esc) {
                            case '"':  sb.append('"'); break;
                            case '\\': sb.append('\\'); break;
                            case '/':  sb.append('/'); break;
                            case 'n':  sb.append('\n'); break;
                            case 'r':  sb.append('\r'); break;
                            case 't':  sb.append('\t'); break;
                            case 'u':
                                String hex = src.substring(pos + 1, Math.min(pos + 5, src.length()));
                                sb.append((char) Integer.parseInt(hex, 16));
                                pos += 4;
                                break;
                            default: sb.append(esc);
                        }
                    }
                } else if (c == '"') {
                    pos++;
                    return sb.toString();
                } else {
                    sb.append(c);
                }
                pos++;
            }
            return sb.toString();
        }

        Number parseNumber() {
            int start = pos;
            if (pos < src.length() && src.charAt(pos) == '-') pos++;
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            boolean isFloat = false;
            if (pos < src.length() && src.charAt(pos) == '.') { isFloat = true; pos++; while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++; }
            if (pos < src.length() && (src.charAt(pos) == 'e' || src.charAt(pos) == 'E')) { isFloat = true; pos++; if (pos < src.length() && (src.charAt(pos) == '+' || src.charAt(pos) == '-')) pos++; while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++; }
            String num = src.substring(start, pos);
            if (isFloat) return Double.parseDouble(num);
            long l = Long.parseLong(num);
            if (l >= Integer.MIN_VALUE && l <= Integer.MAX_VALUE) return (int) l;
            return l;
        }

        Boolean parseBoolean() {
            if (src.startsWith("true", pos)) { pos += 4; return true; }
            if (src.startsWith("false", pos)) { pos += 5; return false; }
            throw new IllegalStateException("Expected boolean at pos " + pos);
        }

        Object parseNull() {
            if (src.startsWith("null", pos)) { pos += 4; return null; }
            throw new IllegalStateException("Expected null at pos " + pos);
        }

        void skipWhitespace() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        void expect(char c) {
            skipWhitespace();
            if (pos < src.length() && src.charAt(pos) == c) { pos++; return; }
            throw new IllegalStateException("Expected '" + c + "' at pos " + pos);
        }
    }
}
