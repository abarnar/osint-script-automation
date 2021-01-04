import shutil
from datetime import datetime
import requests
import os
try:
    import queue
except ImportError:
    import Queue as queue
import threading
import time
import git
import json

username = os.environ.get('GITHUB_USERNAME')
token = os.environ.get('GITHUB_TOKEN')
bulkclonepath = os.environ.get('BULK_CLONE_PATH')
repository = os.environ.get('GITHUB_ORG_NAME')
signFilePath = os.environ.get('SIGNATURE_JSON_FILE')

def time_now():
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    print("date and time =", dt_string)

def main():
    check_env()
    print('starting to get github usernames...')
    time_now()
    usernamelist = getCompleteUserNameList()
    print('total users... ', len(usernamelist))
    print('starting to get repo information of users...')
    infoList = getInfoListForUsers(usernamelist)
    print('total repos... ', len(infoList))
    time_now()

    print('\nstarting next phase ----------- clone repos & deep scan\n')
    cloneBulkRepos(getURLsForBulkClone(infoList), bulkclonepath, 5, username, token)

def check_env():
    if os.environ.get('GITHUB_USERNAME') is None:
        print("Please enter the Github token as an Environment variable!")
        print_required_env()
        exit()

    if os.environ.get('GITHUB_TOKEN') is None:
        print("Please enter the Github repository name as an Environment variable!")
        print_required_env()
        exit()

    if os.environ.get('BULK_CLONE_PATH') is None:
        print("Please enter BULK_CLONE_PATH as an Environment variable!")
        print_required_env()
        exit()

    if os.environ.get('GITHUB_ORG_NAME') is None:
        print("Please enter the Github org name as an Environment variable!")
        print_required_env()
        exit()

def print_required_env():
    print('The Environment variable that has to be set are\n'
          '1.GITHUB_USERNAME\n2.GITHUB_TOKEN\n3.BULK_CLONE_PATH\n4.GITHUB_ORG_NAME')

def getMembersAPIURL():
    return 'https://api.github.com/orgs/' + repository + '/members'

def getRepoAPIUrlForUser(user):
    return 'https://api.github.com/users/' + user + '/repos'

def getCommitsAPIForRepo(user , repo):
    return 'https://api.github.com/repos/' + user + '/' + repo + '/commits'

def getGithubUsernameListFromResponse(responsejson):
    usernamelist = []
    for i in responsejson:
        usernamelist.append(i['login'])
    return usernamelist

def getCompleteUserNameList():
    response = requests.get(getMembersAPIURL(), auth=(username, token))
    if response.status_code == 200 :
        completeUserNameList = getGithubUsernameListFromResponse(response.json())
        while 'next' in response.links:
            response = requests.get(response.links['next']['url'], auth=(username, token))
            completeUserNameList.extend(getGithubUsernameListFromResponse(response.json()))
        return completeUserNameList
    else:
        print(response.json())
        return []

def getInfoListForUsers(usernamelist):
    infoList = []
    for user in usernamelist:
        githubResponseForRepos = requests.get(getRepoAPIUrlForUser(user), auth=(username, token))
        publicReposList = githubResponseForRepos.json()
        for repoJSON in publicReposList:
            if ('fork' in repoJSON) and (repoJSON["fork"]) is False:
                gitHubResponseForCommits = requests.get(getCommitsAPIForRepo(user, repoJSON['name']),auth=(username, token))
                commitsJSON = gitHubResponseForCommits.json()
                if len(commitsJSON) > 0 and not 'message' in commitsJSON :
                    if 'sha' in commitsJSON[0]:
                        latestCommit = commitsJSON[0]['sha']
                        repoMap = constructGithubInfoMapForUser(latestCommit, repoJSON, user)
                        print(repoMap)
                        infoList.append(repoMap)
                else :
                    print(repoJSON['name'] + " : " + commitsJSON['message'])
    return infoList

def constructGithubInfoMapForUser(commit_id, repoJSON, user):
    repoMap = {}
    repoMap['repo_name'] = repoJSON['name']
    repoMap['git_url'] = repoJSON['git_url']
    repoMap['github_user'] = user
    repoMap['commit_id'] = commit_id
    return repoMap

def getURLsForBulkClone(infoList):
    allRepoURLs = []
    for info in infoList:
        allRepoURLs.append(info['git_url'])
    return allRepoURLs

def get_repopath(repo_username, repo_name):
    return repo_username + "/" + repo_name

def parseGitURL(URL, username=None, token=None):
    URL = URL.replace("git://", "https://")
    if (username or token) is not None:
        URL = URL.replace("https://", "https://{0}:{1}@".format(username, token))
    return(URL)

def cloneRepo(URL, cloningpath, username=None, token=None, prefix_mode="directory"):
    repo_username = ""
    try:
        try:
            if not os.path.exists(cloningpath):
                os.mkdir(cloningpath)
                repo_username = URL.split("/")[-2]
            if not os.path.exists(cloningpath + "/" + repo_username):
                os.mkdir(cloningpath + "/" + repo_username)
        except Exception as ex:
            donothing = ""

        URL = parseGitURL(URL, username=username, token=token)
        repo_username = URL.split("/")[-2]
        repo_name = URL.split("/")[-1]
        repopath = get_repopath(repo_username, repo_name)

        if repopath.endswith(".git"):
            repopath = repopath[:-4]
        if '@' in repopath:
            repopath = repopath.replace(repopath[:repopath.index("@") + 1], "")

        fullpath = cloningpath + "/" + repopath
        cloneAndDeepScan(URL, fullpath, repopath)
    except Exception as e:
        print(e)

def cloneAndDeepScan(URL, fullpath, repopath):
    try:
        clone_with_gitpython(URL, fullpath)
    except Exception as e:
        print("exception in cloning repo ============================= ",URL)
        print(e)
        time.sleep(5)
        print("retrying after 5 seconds =============================",URL)
        clone_with_gitpython(URL, fullpath)
    writeDeepScanResult(fullpath, repopath)

    shutil.rmtree(fullpath)


def clone_with_gitpython(URL, fullpath):
    print("cloning repo ", URL)
    if os.path.exists(fullpath):
        git.Repo(fullpath).remote().pull()
    else:
        git.Repo.clone_from(URL, fullpath)


def writeDeepScanResult(fullpath, repopath):
    with open(signFilePath) as f:
        dummy = json.load(f)
    parentlist = dummy.get("signatures")
    for i in parentlist:
        stringtoconcatenate = ""
        if "part" in i and "contents" == i.get("part"):
            if "match" in i:
                stringtoconcatenate = i.get("match")
                stringtoconcatenate = "git grep -Irn \"" + stringtoconcatenate + "$\" "+fullpath+" ; "

            elif "regex" in i:
                stringtoconcatenate = i.get("regex")
                stringtoconcatenate = stringtoconcatenate.replace("^", "")
                stringtoconcatenate = stringtoconcatenate.replace('\\',"\\\\")
                stringtoconcatenate = stringtoconcatenate.replace('/', "\/")
                stringtoconcatenate = "git grep -rnE  \"(" + stringtoconcatenate + ")\" "+fullpath+" ; "
        else:
            if "match" in i:
                stringtoconcatenate = i.get("match")
                stringtoconcatenate = "find "+fullpath+ " -name "+stringtoconcatenate
            elif "regex" in i:
                stringtoconcatenate = i.get("regex")
                stringtoconcatenate = stringtoconcatenate.replace("^", "")
                stringtoconcatenate = stringtoconcatenate.replace('\\', "\\\\")
                stringtoconcatenate = stringtoconcatenate.replace('/', "\/")
                stringtoconcatenate = "find " + fullpath + " -regex \"" + stringtoconcatenate + "\""

        result = os.popen("cd " + fullpath + " ; " + stringtoconcatenate).read()

        if result:
            githublink = str(result).split(':')
            closing = githublink[0].replace(fullpath+"/", "")
            finalclosing = closing.split('\n')
            print("matching for signature : ",i.get("name"), " ", result)
            for i in finalclosing:
                if i:
                    print("https://github.com/"+repopath+"/blob/master/"+i)
            print()

def getRegex():
    regex = '(FC-XSRF-TOKEN)'
    return regex

def cloneBulkRepos(URLs, cloningPath, threads_limit, username=None, token=None, prefix_mode="directory"):
    Q = queue.Queue()
    threads_state = []
    for URL in URLs:
        Q.put(URL)
    while Q.empty() is False:
        if (threading.active_count() < (threads_limit + 1)):
            t = threading.Thread(target=cloneRepo, args=(Q.get(), cloningPath,), kwargs={"username": username, "token": token, 'prefix_mode': prefix_mode})
            # t.daemon = True
            t.start()
        else:
            time.sleep(1)
            threads_state.append(t)
    for _ in threads_state:
        _.join()

if (__name__ == "__main__"):
    main()
