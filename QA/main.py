import build_dict
import _pickle as cPickle
import re
import jieba
import json
import requests


attr_map = build_dict.load_attr_map("attr_mapping.txt") # 属性名统一为一个
attr_ac = cPickle.load(open("attr_ac.pkl","rb")) # 所有的属性名的自动机
ent_dict = build_dict.load_entity_dict("all_entity.txt") # 所有实体名
val_dict = build_dict.load_val_dict("Person_val.txt") # 属性值对应的属性名

def _remove_dup(word_list):
    '''
    args:
        word_list: 一个字符串的list
    '''
    distinct_word_list = []
    for i in range(len(word_list)):
        is_dup = False
        for j in range(len(word_list)):
            if j != i and word_list[i] in word_list[j]:
                is_dup = True
                break
        if not is_dup:
            distinct_word_list.append(word_list[i])
    return distinct_word_list

def _map_predicate(pred_name, map_attr=True):   #找出一个字符串中是否包含知识库中的属性名
    def _map_attr(word_list):
        ans = []
        for word in word_list:
            ans.append(attr_map[word][0])
        return ans

    match = []
    for w in attr_ac.iter(pred_name):
        match.append(w[1][1])
    if not len(match):
        return []
    ans = _remove_dup(match)
    if map_attr:
        ans = _map_attr(ans)
    return ans

def _generate_ngram_word(word_list_gen):
    '''
    args:
        word_list_gen: 一个字符串的迭代器
    '''
    word_list = []
    for w in word_list_gen:
        word_list.append(w)
    n = len(word_list)
    ans = []
    for i in range(1, n + 1):
        for j in range(0, n + 1 - i):
            ans.append(''.join(word_list[j:j+i]))
    return ans

def _entity_linking(entity_name):    #找出一个字符串中是否包含知识库中的实体，这里是字典匹配，可以用检索代替
    parts = re.split(r'的|是|有', entity_name)
    ans = []
    for p in parts:
        pp = jieba.cut(p)
        if pp is not None:
            for phrase in _generate_ngram_word(pp): #分词结果的n-gram查找
                if phrase in ent_dict: #匹配字典，数据量大时可以用搜索ES代替
                    ans.append(phrase)
    return ans

def _val_linking(nl_query):
    parts = re.split(r'的|是|有', nl_query)
    hit_val = []
    for p in parts:
        for phrase in _generate_ngram_word(p):
            if phrase in val_dict:
                hit_val.append(phrase)
    hit_val = _remove_dup(hit_val)
    ans = {}
    for p in hit_val:
        ans[p] = val_dict[p]
    return ans

def translate_NL2LF(nl_query):
    '''
    使用基于模板的方法将自然语言查询转化为logic form
    '''
    entity_list = _entity_linking(nl_query) #识别实体名
    attr_list = _map_predicate(nl_query, map_attr=False) #识别属性名
    lf_query = ""
    if entity_list: #识别到实体
        if not attr_list: #### 问题类别： 查询单个实体 ####
            lf_query = entity_list[0] #生成对应的Logical form
        else:
            first_entity_pos = nl_query.find(entity_list[0])
            first_attr_pos = nl_query.find(attr_list[0])
            if len(attr_list) == 1: #### 问题类别： 单个实体属性查询 ####
                if first_entity_pos < first_attr_pos: #判断实体名和属性名的出现位置
                    lf_query = "{}:{}".format(entity_list[0], attr_list[0]) #SP 生成对应的Logical form
                else:
                    lf_query = "{}:{}".format(attr_list[0], entity_list[0]) #PO 生成对应的Logical form
            else: #### 问题类别: 多跳查询 ####
                lf_query = entity_list[0]
                for pred in attr_list:
                    lf_query += ":" + pred #生成对应的Logical form
    else: #### 问题类别： 多个属性条件检索实体 ####
        val_d = _val_linking(nl_query) #识别属性值-名
        attr_pos = {}
        val_pos = {}
        for a in attr_list:
            attr_pos[a] = nl_query.find(a)
        for v in val_d:
            val_pos[v] = nl_query.find(v)
        retain_attr = []
        for a in attr_pos:
            to_retain = True
            for v in val_pos:
                if (attr_pos[a] >= val_pos[v] and attr_pos[a] + len(a) <= val_pos[v] + len(v)) or \
                        (val_d[v] == a and attr_pos[a] + len(a) >= val_pos[v] - 2):
                    to_retain = False
                    break
            if to_retain:
                retain_attr.append(a)
        tmp = {}
        for v in val_pos:
            to_retain = True
            for a in attr_pos:
                if (val_pos[v] >= attr_pos[a] and val_pos[v] + len(v) <= attr_pos[a] + len(a)):
                    to_retain = False
                    break
            if to_retain:
                tmp[v] = val_d[v]
        val_d = tmp

        final_val_d = {}
        for v in val_d:
            if not (v.isdigit() or v in '大于' or v in '小于'):
                final_val_d[v] = val_d[v]

        part_queries = []
        for a in retain_attr:
            mapped_a = attr_map[a][0]
            part_query = ""
            if mapped_a == 'height':
                height = re.findall('\d{1,3}', nl_query[attr_pos[a]:])[0]
                height_pos = attr_pos[a] + nl_query[attr_pos[a]:].find(height)
                between = nl_query[attr_pos[a] + len(a):height_pos]
                if re.search('大于等于|不小于|>=|不矮于', between):
                    part_query = "身高>=" + height
                elif re.search('小于等于|不超过|<=|不大于', between):
                    part_query = "身高<=" + height
                elif re.search('大于|高于|超过|>', between) or (
                        between == '比' and nl_query[height_pos + len(height)] in ['高', '大']):
                    part_query = "身高>" + height
                elif re.search('小于|矮于|<', between) or (
                        between == '比' and nl_query[height_pos + len(height)] in ['矮', '小']):
                    part_query = "身高<" + height
                elif re.search('等于|=|是', between):
                    part_query = "身高:" + height
            elif mapped_a == 'weight':
                weight = re.findall('\d{1,3}', nl_query[attr_pos[a]:])[0]
                weight_pos = attr_pos[a] + nl_query[attr_pos[a]:].find(weight)
                between = nl_query[attr_pos[a] + len(a):weight_pos]
                if re.search('大于等于|不小于|>=|不轻于', between):
                    part_query = "体重>=" + weight
                elif re.search('小于等于|不超过|<=|不大于', between):
                    part_query = "体重<=" + weight
                elif re.search('大于|重于|超过|>|高于', between) or (
                        between == '比' and nl_query[weight_pos + len(weight)] in ['重', '大']):
                    part_query = "体重>" + weight
                elif re.search('小于|轻于|<', between) or (
                        between == '比' and nl_query[weight_pos + len(weight)] in ['轻', '小']):
                    part_query = "体重<" + weight
                elif re.search('等于|=|是', between):
                    part_query = "体重:" + weight
            part_queries.append(part_query)

        for q in part_queries:
            if not lf_query:
                lf_query += q
            else:
                lf_query += ' AND ' + q

        prev_pred = []
        for v in final_val_d:
            pred = final_val_d[v]
            if pred in prev_pred:
                lf_query += ' OR ' + '{}:{}'.format(pred, v)
            else:
                if not lf_query:
                    lf_query = '{}:{}'.format(pred, v)
                else:
                    lf_query += ' AND ' + '{}:{}'.format(pred, v)
                prev_pred.append(pred)
    return lf_query

def _search_single_subj(entity_name): # 用实体名得到实体相关的所有信息
    query = json.dumps({"query": { "bool":{"filter":{"term" :{"subj" : entity_name}}}}})
    response = requests.get("http://localhost:9200/person/_search", headers={"Content-Type":"application/json"}, data=query)
    res = json.loads(response.content)
    if res['hits']['total'] == 0:
        return None, 'entity'
    else:
        card = dict()
        card['subj'] = entity_name
        s = res['hits']['hits'][0]['_source']
        if 'height' in s:
            card['height'] = s['height']
        if 'weight' in s:
            card['weight'] = s['weight']
        for po in s['po']:
            if po['pred'] in card:
                card[po['pred']] += ' ' + po['obj']
            else:
                card[po['pred']] = po['obj']
        return card, 'done'

def _search_multihop_SP(parts): # 多跳
    has_done = parts[0]
    v = parts[0]
    for i in range(1, len(parts)):
        en = _entity_linking(v)
        if not len(en):
            return '执行到: ' + has_done, '==> 对应的结果为:' + v + ', 知识库中没有该实体: ' + v
        card, msg = _search_single_subj(en[-1])
        p = _map_predicate(parts[i])
        if not len(p):
            return '执行到: ' + has_done, '==> 知识库中没有该属性: ' + parts[i]
        p = p[0]
        if p not in card:
            return '执行到: ' + has_done, '==> 实体 ' + card['subj'] + ' 没有属性 ' + p
        v = card[p]
        if isinstance(v, int):
            v = str(v)
        has_done += ":" + parts[i]
    return v, 'done'


def _search_multi_PO(exps, bool_ops):
    po_list = []
    cmp_dir = {
        "<": "lt",
        "<=": "lte",
        ">": "gt",
        ">=": "gte"
    }

    for e in exps:
        if e == "":
            return "", 'AND 或 OR 后不能为空'

        begin_with_NOT = False
        if e[0:3] == 'NOT':
            begin_with_NOT = True
            e = e[3:]
        elif 'NOT' in e:
            return e, 'NOT请放在PO对前面'

        op = re.findall("：|:|>|<|>=|<=", e)
        if len(op) != 1:
            return e, '语法错误'
        op = op[0]
        if op == '<' or op == '>':
            index = e.find(op)
            if e[index + 1] == '=':
                op = op + '='
        pred, obj = e.split(op)
        c_pred = _map_predicate(pred)
        if not len(c_pred):
            return e, '知识库中没有该属性: ' + pred
        if obj == '':
            return e + "?", '属性值不能为空'
        pred = c_pred[0]

        part_query = ""
        if not begin_with_NOT:
            if op == ':' or op == '：':
                if pred == 'height' or pred == 'weight':
                    part_query = '{"term":{"' + pred + '":' + obj + '}}'
                else:
                    part_query = '{"nested":{"path":"po","query":{"bool":{"must":[{"term":{"po.pred":"' + pred + \
                                 '"}},{"term":{"po.obj":"' + obj + '"}}]}}}}'
            else:
                if pred == 'height' or pred == 'weight':
                    part_query = '{"range":{"' + pred + '":{"' + cmp_dir[op] + '":' + obj + '}}}'
                else:
                    return e, '该属性不支持比较大小,目前只支持height,weight'
        else:
            if op == ':' or op == '：':
                if pred == 'height' or pred == 'weight':
                    part_query = '{"bool":{"must_not":{"term":{"' + pred + '":' + obj + '}}}}'
                else:
                    part_query = '{"nested":{"path":"po","query":{"bool":{"must":[{"term":{"po.pred":"' + pred + \
                                 '"}},{"bool":{"must_not":{"term":{"po.obj":"' + obj + '"}}}}]}}}}'
            else:
                if pred == 'height' or pred == 'weight':
                    part_query = '{"bool":{"must_not":{"range":{"' + pred + '":{"' + cmp_dir[op] + '":' + obj + \
                                 '}}}}}'
                else:
                    return e, '该属性不支持比较大小,目前只支持height,weight'
        po_list.append(part_query)

    or_po = [False] * len(exps)
    should_list = []
    must_list = []
    i = 0
    while i < len(bool_ops):
        if bool_ops[i] == 'OR':
            adjacent_or = [po_list[i]]
            or_po[i] = True
            while i < len(bool_ops) and bool_ops[i] == 'OR':
                adjacent_or.append(po_list[i + 1])
                or_po[i + 1] = True
                i += 1
            should_list.append(",".join(adjacent_or))
        i += 1
    for i, po in enumerate(or_po):
        if not po:
            must_list.append(po_list[i])
    must_list = ",".join(must_list)
    query = ""
    if must_list:
        query = '{"query":{"bool":{"must":[' + must_list + ']'
        if should_list:
            query += ","
            for s in should_list:
                query += '"should":[' + s + '],'
            query = query[:-1]
        query += '}}}'
    else:
        query = '{"query":{"bool":{'
        if should_list:
            for s in should_list:
                query += '"should":[' + s + '],'
            query = query[:-1]
        query += '}}}'

    query = query.encode('utf-8')
    response = requests.get("http://localhost:9200/person/_search", headers={"Content-Type":"application/json"}, data=query)
    res = json.loads(response.content)

    if res['hits']['total'] == 0:
        return None, 'none'
    else:
        ans = {}
        for e in res['hits']['hits']:
            name = e['_source']['subj']
            ans[name] = "/search?question=" + name

        return ans, 'done'

def _parse_query(question):
    answer, query_type = "", None
    question = question.upper()
    question = question.replace(" ","")
    parts = re.split("：|:|<|>|<=|>=", question)
    en = _entity_linking(parts[0])
    if len(parts) < 2:
        if len(en):
            answer,msg = _search_single_subj(en[-1])
        else:
            return question, '未识别到实体',-1
    elif 'AND' in question or 'OR' in question:
        bool_ops = re.findall('AND|OR',question)
        exps = re.split('AND|OR',question)
        answer, msg = _search_multi_PO(exps, bool_ops)
    elif len(_map_predicate(parts[0])) != 0:
        answer, msg = _search_multi_PO([question],[])
    elif len(en):
        answer, msg = _search_multihop_SP(parts)
    else:
        msg = '未识别到实体或属性: ' + parts[0]
    return answer, msg


if __name__ == '__main__':
    # print(_map_predicate('姚明重量和身高'))
    # print(_entity_linking('姚明的重量和身高'))
    # print(_val_linking('姚明的重量和身高'))
    # print(_search_single_subj('姚明'))
    # print(_search_multihop_SP(['姚明','女儿','母亲']))

    # print(_parse_query(translate_NL2LF('姚明是在哪儿出生的')))
    # print(_parse_query(translate_NL2LF('姚明的女儿的母亲')))
    # print(_parse_query(translate_NL2LF('身高>200,体重小于200的中国篮球运动员')))
    print(_parse_query(translate_NL2LF('谁的老公是姚明')))
