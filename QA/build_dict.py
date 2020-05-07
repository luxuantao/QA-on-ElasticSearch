import ahocorasick
import _pickle as cPickle
from collections import defaultdict


entity_list_file = 'all_entity.txt' # 所有的实体名
entity_out_path = 'ent_ac.pkl'
attr_list_file = 'attr_mapping.txt' # 属性同义词
attr_out_path = 'attr_ac.pkl'
val_list_file = 'Person_val.txt' # 属性值-属性

def dump_ac_entity_dict(list_file, out_path): # 所有的实体名
    A = ahocorasick.Automaton()
    f = open(list_file, 'r', encoding='utf-8')
    i = 0
    for line in f:
        word = line.strip()
        A.add_word(word, (i, word))
        i += 1
    A.make_automaton()
    cPickle.dump(A, open(out_path, "wb"))
    f.close()

def dump_ac_attr_dict(attr_mapping_file, out_path): # 所有的属性
    A = ahocorasick.Automaton()
    f = open(attr_mapping_file, 'r', encoding='utf-8')
    i = 0
    for line in f.readlines():
        parts = line.strip().split(" ")
        for p in parts:
            if p != "":
                A.add_word(p, (i, p))
                i += 1
    A.make_automaton()
    cPickle.dump(A, open(out_path, 'wb'))
    f.close()

def load_ac_dict(out_path):
    A = cPickle.load(open(out_path, "rb"))
    return A

def load_attr_map(attr_mapping_file): # 所有的同类属性映射为一个
    f = open(attr_mapping_file, 'r', encoding='utf-8')
    mapping = defaultdict(list)
    for line in f.readlines():
        parts = line.strip().split(" ")
        for p in parts:
            if p != '':
                mapping[p].append(parts[0])
    f.close()
    return mapping

def load_entity_dict(entity_file): # 出现过的实体名
    f = open(entity_file, 'r', encoding='utf-8')
    ents = {}
    for line in f.readlines():
        ents[line.strip()] = 1
    f.close()
    return ents

def load_val_dict(val_file): # 属性值2属性
    f = open(val_file, 'r', encoding='utf-8')
    val_attr_map = {}
    for line in f.readlines():
        try:
            parts = line.strip().split(" ")
            val_attr_map[parts[0]] = parts[1]
        except Exception:
            pass
    f.close()
    return val_attr_map


if __name__ == '__main__':    
    # dump_ac_attr_dict(attr_list_file, attr_out_path)
    # dump_ac_entity_dict(entity_list_file, entity_out_path)
    # load_val_dict(val_list_file)
    print(load_attr_map(attr_list_file))