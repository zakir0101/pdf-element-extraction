import re

split_patter = r"(?:(?:[^\\\n]|^)(?P<arry>\[(?:.*?[^\\])?\]))"
array_pattern_old = r"(?:(?P<pre>[^\\\n]|^)\[(?P<array>.*?[^\\])?\])"
array_pattern  = r"(?P<empty_str>\(\))|(?:\((?P<string>(?:.*?[^\\]))(?=\)))|(?:(?:[^_\-\n\d]|^)(?P<number>\d+))|(?P<nnumber>-\d+)"
primative_patter = r"(?:(?P<number>-?\d+)|(?:\((?P<string>(?:.*?[^\\])?)\)))"

test = r" (\\251 U\( sdf\)CLES 202)-7(3)-7( )-20429(9702/12/F/)-7(M)-1(/23)-7( )-27304( )   slkdfj[99304(klsjfj)]cmd   slkdfj[99304(klsjfj)]cmd  slkdfj[99304(klsjfj)]cmd  [(\251 U\( sdf\)CLES 202)-7(3)-7( )-20429(9702/12/F/)-7(M)-1(/23)-7( )-27304( )]TJ "

counter_prim = 0
def extract_array(test = test):
    arrays = {}
    global counter 
    counter = 0
    def replace(match):
        global counter
        counter += 1
        array_name = f"ARRAY__{counter}"
        array = match.group("array") 
        pre = match.group("pre")
        if not array:
            arrays[array_name] = [] 
            return f"{pre} "

        arrays[array_name] = [] 
        extract_primatives(array,arrays[array_name]) 
        return f"{match.group('pre')}  ARRAY__{counter} "


    new_string = re.sub(array_pattern,replace, test, flags= re.MULTILINE | re.DOTALL)
    return new_string, arrays

def extract_primatives(data : str ,prim_array = []):
    global counter_prim  
    counter_prim = 0
    prim_dict = {}
    def replace(match):
        global counter_prim
        counter_prim += 1

        for p_type , p_value in match.groupdict().items(): 

        number = match.group("number")
        string = match.group("string")
        if number:
            prim_dict[f"NUMBER__{counter_prim}"] = int(number)
            prim_array.append(int(number))
            return f" NUMBER__{counter_prim} "
        if string:
            prim_dict[f"STRING__{counter_prim}"] = string
            prim_array.append(string)
            return f" STRING__{counter_prim} "
        return f" "
    
    new_string = re.sub(primative_patter,replace, data, flags = re.MULTILINE | re.DOTALL)
    return new_string, prim_dict
test, arrays = extract_array(test)
new_string, prim_dict = extract_primatives(test)
# new_string, arrays = extract_array(test)
print(new_string)
print(prim_dict)
print(arrays)
